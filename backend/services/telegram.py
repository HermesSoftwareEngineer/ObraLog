import os
import sys
import threading
import re
import uuid
import asyncio
import logging
from datetime import datetime

from langchain_core.messages import HumanMessage
from telegram import Bot
from telegram.error import TelegramError
from telegram.request import HTTPXRequest

try:
	from backend.agents.graph import graph
except ImportError:
	from agents.graph import graph

from backend.db.repository import Repository
from backend.db.session import SessionLocal
from backend.agents.llms import transcribe_audio_bytes
from backend.services.telegram_interactions import get_poll_context


_POLLING_LOCK = threading.Lock()
_POLLING_STARTED = False
_BOT = None

logger = logging.getLogger(__name__)


def _log_info(message: str):
	"""Log info com print e flush garantido."""
	print(f"[TELEGRAM] {message}", flush=True)
	logger.info(message)


def _log_warning(message: str):
	"""Log warning com print e flush garantido."""
	print(f"[TELEGRAM-WARN] {message}", flush=True)
	logger.warning(message)


def _log_error(message: str, exc_info=False):
	"""Log error com print e flush garantido."""
	print(f"[TELEGRAM-ERROR] {message}", flush=True)
	logger.error(message, exc_info=exc_info)


def _log_debug(message: str):
	"""Log debug com print e flush garantido."""
	logger.debug(message)


def _get_bot() -> Bot:
	"""Retorna a instância do bot Telegram."""
	global _BOT
	if _BOT is None:
		token = os.environ.get("TELEGRAM_TOKEN")
		if not token:
			raise RuntimeError("TELEGRAM_TOKEN não configurado no .env")
		
		request = HTTPXRequest(connect_timeout=10, read_timeout=30)
		_BOT = Bot(token=token, request=request)
	
	return _BOT


async def _telegram_api_call_async(method_name: str, **kwargs) -> dict:
	"""Realiza chamada à API Telegram de forma assíncrona com retry."""
	bot = _get_bot()
	retries = 3
	
	logger.debug(f"[API_CALL] Iniciando chamada: {method_name} com args: {list(kwargs.keys())}")
	
	for attempt in range(retries):
		try:
			method = getattr(bot, method_name)
			logger.debug(f"[API_CALL] Tentativa {attempt + 1}/{retries}: {method_name}")
			result = await method(**kwargs)
			print(f"[API_CALL] Sucesso em {method_name}", flush=True)
			logger.info(f"[API_CALL] Sucesso em {method_name}")
			return {"ok": True, "result": result}
		except TelegramError as exc:
			logger.warning(f"[API_CALL] TelegramError na tentativa {attempt + 1}/{retries}: {exc}")
			if attempt == retries - 1:
				logger.error(f"[API_CALL] Falha final em {method_name} após {retries} tentativas: {exc}")
				raise RuntimeError(f"Erro na API do Telegram: {exc}") from exc
			wait = 2 ** attempt
			logger.warning(f"[API_CALL] Aguardando {wait}s antes da retentativa...")
			await asyncio.sleep(wait)
		except Exception as exc:
			logger.error(f"[API_CALL] Erro inesperado em {method_name}: {type(exc).__name__}: {exc}", exc_info=True)
			if attempt == retries - 1:
				raise RuntimeError(f"Erro ao chamar API do Telegram: {exc}") from exc
			wait = 2 ** attempt
			await asyncio.sleep(wait)
	
	return {"ok": False}


def send_message(chat_id: int | str, text: str) -> None:
	"""Envia mensagem de forma síncrona (compatibilidade com código existente)."""
	logger.debug(f"[SEND_MSG] Iniciando envio para chat_id={chat_id}, tamanho_texto={len(text)}")
	try:
		loop = asyncio.get_event_loop()
		if loop.is_running():
			# Se já há um loop rodando, cria uma tarefa
			logger.debug(f"[SEND_MSG] Loop já rodando, criando task")
			asyncio.create_task(_telegram_api_call_async("send_message", chat_id=chat_id, text=text))
		else:
			logger.debug(f"[SEND_MSG] Loop não rodando, executando sync")
			loop.run_until_complete(_telegram_api_call_async("send_message", chat_id=chat_id, text=text))
	except RuntimeError as e:
		logger.debug(f"[SEND_MSG] RuntimeError (sem loop), criando novo: {e}")
		# Sem event loop, create novo
		asyncio.run(_telegram_api_call_async("send_message", chat_id=chat_id, text=text))
	except Exception as e:
		logger.error(f"[SEND_MSG] ERRO inesperado ao enviar: {e}", exc_info=True)
		raise


def set_webhook(base_url: str) -> None:
	"""Configura o webhook do Telegram (síncrono)."""
	if not base_url:
		raise RuntimeError("PUBLIC_BASE_URL não configurada para registrar webhook.")

	webhook_url = f"{base_url.rstrip('/')}/telegram/webhook"
	secret_token = os.environ.get("TELEGRAM_WEBHOOK_SECRET_TOKEN")
	logger.info(f"Configurando webhook do Telegram para: {webhook_url}")
	
	try:
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		loop.run_until_complete(
			_telegram_api_call_async("set_webhook", url=webhook_url, secret_token=secret_token)
		)
		loop.close()
		logger.info("Webhook configurado com sucesso")
	except Exception as e:
		logger.error(f"Erro ao configurar webhook: {e}")
		raise


def _extract_text_content(content) -> str:
	"""Extrai conteúdo de texto de uma resposta do agente."""
	if isinstance(content, str):
		logger.debug(f"[EXTRACT] Conteúdo é string: {content[:50]}...")
		return content

	if isinstance(content, list):
		logger.debug(f"[EXTRACT] Conteúdo é list com {len(content)} itens")
		parts = []
		for i, item in enumerate(content):
			if isinstance(item, str):
				parts.append(item)
				logger.debug(f"[EXTRACT] Item {i}: string")
			elif isinstance(item, dict):
				text_value = item.get("text")
				if isinstance(text_value, str):
					parts.append(text_value)
					logger.debug(f"[EXTRACT] Item {i}: dict com 'text'")
				else:
					logger.debug(f"[EXTRACT] Item {i}: dict sem 'text' válido. Keys: {item.keys()}")
			else:
				logger.debug(f"[EXTRACT] Item {i}: tipo {type(item).__name__}")
		result = "\n".join(part for part in parts if part).strip()
		logger.debug(f"[EXTRACT] Resultado list: {result[:50] if result else 'VAZIO'}...")
		return result

	if isinstance(content, dict):
		logger.debug(f"[EXTRACT] Conteúdo é dict com keys: {content.keys()}")
		text_value = content.get("text")
		if isinstance(text_value, str):
			logger.debug(f"[EXTRACT] Extrato dict: {text_value[:50]}...")
			return text_value
		logger.debug(f"[EXTRACT] Dict sem 'text' válido")

	result = str(content)
	logger.debug(f"[EXTRACT] Conversão final para string: {result[:50]}...")
	return result


def _response_used_telegram_ui(messages: list) -> bool:
	# Check only messages after the last HumanMessage to avoid old history matches
	recent_messages = []
	for msg in reversed(messages):
		if getattr(msg, "type", "") == "human" or type(msg).__name__ == "HumanMessage":
			break
		recent_messages.append(msg)
		
	for msg in recent_messages:
		content = getattr(msg, "content", "")
		if not isinstance(content, str):
			continue
		if "'telegram_ui_dispatched': True" in content or '"telegram_ui_dispatched": True' in content:
			return True
	return False


async def get_updates_async(offset: int | None = None) -> list:
	"""Obtém updates do Telegram de forma assíncrona."""
	bot = _get_bot()
	try:
		updates = await bot.get_updates(
			offset=offset,
			timeout=30,
			allowed_updates=["message", "callback_query"]
		)
		return [u.to_dict() for u in updates]
	except TelegramError as e:
		logger.error(f"Erro ao buscar updates: {e}")
		raise RuntimeError(f"Erro na API do Telegram.") from e


def get_updates(offset: int | None = None) -> list:
	"""Wrapper síncrono para compatibilidade com código existente."""
	try:
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		result = loop.run_until_complete(get_updates_async(offset))
		loop.close()
		return result
	except Exception as e:
		logger.error(f"Erro em get_updates: {e}")
		raise


async def _download_telegram_file_async(file_id: str) -> tuple[bytes, str]:
	"""Baixa arquivo do Telegram de forma assíncrona."""
	bot = _get_bot()
	
	try:
		file_obj = await bot.get_file(file_id)
		file_bytes = await file_obj.download_as_bytearray()
		
		# Determina MIME type baseado na extensão
		file_path = file_obj.file_path or ""
		mime_type = "audio/ogg"  # default
		
		if file_path.endswith(".mp3"):
			mime_type = "audio/mpeg"
		elif file_path.endswith(".wav"):
			mime_type = "audio/wav"
		elif file_path.endswith(".m4a"):
			mime_type = "audio/mp4"
		
		return bytes(file_bytes), mime_type
	except TelegramError as e:
		logger.error(f"Erro ao baixar arquivo do Telegram: {e}")
		raise RuntimeError(f"Erro ao baixar arquivo: {e}") from e


def _download_telegram_file(file_id: str) -> tuple[bytes, str]:
	"""Wrapper síncrono para compatibilidade."""
	try:
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		result = loop.run_until_complete(_download_telegram_file_async(file_id))
		loop.close()
		return result
	except Exception as e:
		logger.error(f"Erro em _download_telegram_file: {e}")
		raise


def _extract_message_text_or_transcription(message: dict, chat_id: int | str) -> str | None:
	text = message.get("text")
	if text:
		return text

	photos = message.get("photo") or []
	if photos:
		token = os.environ.get("TELEGRAM_TOKEN")
		if not token:
			raise RuntimeError("TELEGRAM_TOKEN não configurado.")

		biggest_photo = photos[-1]
		file_id = biggest_photo.get("file_id")
		if not file_id:
			raise RuntimeError("Imagem recebida sem file_id.")

		try:
			# Obtém o URL da imagem usando a API
			bot = _get_bot()
			loop = asyncio.new_event_loop()
			asyncio.set_event_loop(loop)
			file_obj = loop.run_until_complete(bot.get_file(file_id))
			loop.close()
			
			image_url = f"https://api.telegram.org/file/bot{os.environ.get('TELEGRAM_TOKEN')}/{file_obj.file_path}"
		except Exception as e:
			logger.warning(f"Não foi possível obter URL da imagem: {e}")
			image_url = f"telegram://{file_id}"
		
		caption = (message.get("caption") or "").strip()
		if caption:
			return (
				f"Recebi uma imagem para registro. URL da imagem: {image_url}. "
				f"Descrição enviada pelo usuário: {caption}"
			)
		return f"Recebi uma imagem para registro. URL da imagem: {image_url}"

	voice = message.get("voice")
	audio = message.get("audio")
	audio_payload = voice or audio
	if not audio_payload:
		return None

	send_message(chat_id, "Recebi seu áudio, estou ouvindo...")
	file_id = audio_payload.get("file_id")
	if not file_id:
		raise RuntimeError("Áudio recebido sem file_id.")

	audio_bytes, mime_type = _download_telegram_file(file_id)
	transcription = transcribe_audio_bytes(audio_bytes, mime_type).strip()
	if not transcription:
		raise RuntimeError("Não consegui transcrever o áudio.")
	return transcription


def _extract_link_code(text: str) -> str | None:
	if not text:
		return None

	patterns = [
		r"^/VINCULAR\s+([A-Z0-9]{6,12})$",
		r"^VINCULAR\s+([A-Z0-9]{6,12})$",
		r"^CODIGO\s+([A-Z0-9]{6,12})$",
		r"^([A-Z0-9]{8})$",
	]

	normalized = text.strip().upper()
	for pattern in patterns:
		match = re.match(pattern, normalized)
		if match:
			return match.group(1)
	return None


def _normalize_chat_id(chat_id: int | str) -> str:
	return str(chat_id)


def _new_thread_id(chat_id: int | str) -> str:
	chat_key = _normalize_chat_id(chat_id)
	return f"{chat_key}:{uuid.uuid4().hex}"


def _resolve_thread_id(usuario, chat_id: int | str) -> str:
	stored = getattr(usuario, "telegram_thread_id", None)
	if isinstance(stored, str) and stored.strip():
		return stored
	return _normalize_chat_id(chat_id)


def _is_reset_context_command(text: str) -> bool:
	if not text:
		return False

	normalized = text.strip().lower()
	reset_commands = {
		"/nova_thread",
		"/novathread",
		"/reset_contexto",
		"/reset",
		"/limpar_contexto",
		"/zerar_contexto",
	}
	return normalized in reset_commands


def _conversation_date_payload() -> dict:
	now = datetime.now()
	return {
		"conversation_date": now.date().isoformat(),
		"conversation_date_br": now.strftime("%d/%m/%Y"),
	}


def _build_poll_answer_text(question: str, selected_options: list[str]) -> str:
	if not selected_options:
		return f"Resposta de enquete recebida. Pergunta: {question}. Nenhuma opção selecionada."
	return (
		f"Resposta de enquete recebida. Pergunta: {question}. "
		f"Opções selecionadas: {', '.join(selected_options)}."
	)


def _handle_poll_answer_update(poll_answer: dict) -> dict:
	poll_id = poll_answer.get("poll_id")
	if not poll_id:
		return {"ok": True, "ignored": True, "reason": "poll_answer_sem_poll_id"}

	context = get_poll_context(str(poll_id))
	if not context:
		return {"ok": True, "ignored": True, "reason": "poll_context_nao_encontrado"}

	chat_id = context.get("chat_id")
	thread_id = context.get("thread_id")
	telegram_message_thread_id = context.get("telegram_message_thread_id")
	actor_user_id = context.get("actor_user_id")
	actor_level = context.get("actor_level")
	question = context.get("question") or "Checklist"
	options = context.get("options") or []
	option_ids = poll_answer.get("option_ids") or []

	selected_options = []
	for option_id in option_ids:
		if isinstance(option_id, int) and 0 <= option_id < len(options):
			selected_options.append(options[option_id])

	poll_response_text = _build_poll_answer_text(question, selected_options)

	if not chat_id or thread_id is None or actor_user_id is None or actor_level is None:
		return {"ok": True, "ignored": True, "reason": "poll_context_incompleto"}

	with SessionLocal() as db:
		usuario = Repository.usuarios.obter_por_id(db, int(actor_user_id))

	if not usuario:
		send_message(chat_id, "Recebi a resposta da enquete, mas não localizei o usuário vinculado no sistema.")
		return {"ok": False, "chat_id": chat_id, "reason": "usuario_enquete_nao_encontrado"}

	chat_user = poll_answer.get("user") or {}
	chat_display_name = (
		chat_user.get("first_name")
		or chat_user.get("username")
		or usuario.nome
		or str(chat_id)
	)

	config = {
		"configurable": {
			"thread_id": str(thread_id),
			"telegram_chat_id": str(chat_id),
			"telegram_message_thread_id": int(telegram_message_thread_id) if telegram_message_thread_id is not None else None,
			**_conversation_date_payload(),
			"actor_user_id": usuario.id,
			"actor_level": usuario.nivel_acesso.value if hasattr(usuario.nivel_acesso, "value") else str(usuario.nivel_acesso),
			"actor_name": usuario.nome,
			"actor_chat_display_name": chat_display_name,
		}
	}

	response = graph.invoke({"messages": [HumanMessage(content=poll_response_text)]}, config)
	response_messages = response["messages"]
	ui_dispatched = _response_used_telegram_ui(response_messages)
	reply = _extract_text_content(response_messages[-1].content)
	if not reply:
		reply = "Resposta da enquete recebida."
	if not ui_dispatched:
		send_message(chat_id, reply)
	return {"ok": True, "chat_id": chat_id, "reason": "poll_answer_processado", "poll_id": poll_id}


def handle_telegram_update(update: dict) -> dict:
	poll_answer = update.get("poll_answer")
	if poll_answer:
		return _handle_poll_answer_update(poll_answer)

	message = update.get("message") or update.get("edited_message")
	if not message:
		_log_debug("Update ignorado: sem mensagem")
		return {"ok": True, "ignored": True}

	chat = message.get("chat") or {}
	chat_id = chat.get("id")
	if chat_id is None:
		_log_error("Chat inválido no update do Telegram")
		raise RuntimeError("Chat inválido no update do Telegram.")

	chat_display_name = (
		chat.get("first_name")
		or chat.get("username")
		or str(chat_id)
	)
	telegram_message_thread_id = message.get("message_thread_id")

	_log_info(f"Nova mensagem recebida - chat_id={chat_id}, usuario={chat_display_name}")

	text = _extract_message_text_or_transcription(message, chat_id)
	if not text:
		logger.debug(f"[TELEGRAM] Mensagem ignorada (sem texto) - chat_id={chat_id}")
		return {"ok": True, "ignored": True}
	
	_log_info(f"Texto extraído: {text[:100]}... (chat_id={chat_id})")

	with SessionLocal() as db:
		usuario = Repository.usuarios.obter_por_telegram_chat_id(db, str(chat_id))

	if not usuario:
		_log_warning(f"Usuário não vinculado - chat_id={chat_id}")
		link_code = _extract_link_code(text)
		if link_code:
			_log_info(f"Tentando vínculo com código: {link_code}")
			with SessionLocal() as db:
				code_item = Repository.telegram_link_codes.obter_valido_por_codigo(db, link_code)
				if not code_item:
					_log_warning(f"Código inválido/expirado: {link_code}")
					send_message(chat_id, "Código inválido ou expirado. Peça um novo código ao administrador.")
					return {"ok": False, "chat_id": chat_id, "reason": "codigo_invalido"}

				target_user = Repository.usuarios.obter_por_id(db, code_item.user_id)
				if not target_user:
					_log_error(f"Usuário do código não encontrado (user_id={code_item.user_id})")
					send_message(chat_id, "Usuário do código não encontrado. Solicite um novo código.")
					return {"ok": False, "chat_id": chat_id, "reason": "usuario_codigo_inexistente"}

				existing_chat_user = Repository.usuarios.obter_por_telegram_chat_id(db, str(chat_id))
				if existing_chat_user and existing_chat_user.id != target_user.id:
					_log_error(f"Chat já vinculado a outro usuário - chat_id={chat_id}")
					send_message(chat_id, "Este Telegram já está vinculado a outro usuário.")
					return {"ok": False, "chat_id": chat_id, "reason": "chat_ja_vinculado"}

				Repository.usuarios.atualizar(
					db,
					target_user.id,
					telegram_chat_id=str(chat_id),
					telegram_thread_id=str(chat_id),
				)
				Repository.telegram_link_codes.marcar_usado(db, code_item.id)
				_log_info(f"Vínculo concluído - user_id={target_user.id}, chat_id={chat_id}")

			send_message(chat_id, "Vínculo concluído com sucesso. Agora você já pode usar o assistente.")
			return {"ok": True, "chat_id": chat_id, "reason": "vinculado_por_codigo"}

		_log_debug(f"Usuário não vinculado e sem código - chat_id={chat_id}")
		send_message(
			chat_id,
			"Seu usuário ainda não está vinculado no sistema. Peça ao administrador um código de vínculo e envie: /vincular SEU_CODIGO",
		)
		return {"ok": False, "chat_id": chat_id, "reason": "usuario_nao_vinculado"}

	if _is_reset_context_command(text):
		_log_info(f"Comando de reset de contexto - chat_id={chat_id}, user_id={usuario.id}")
		with SessionLocal() as db:
			usuario_db = Repository.usuarios.obter_por_id(db, usuario.id)
			if not usuario_db:
				_log_error(f"Usuário não encontrado para reset - user_id={usuario.id}")
				send_message(chat_id, "Não encontrei seu usuário para reiniciar o contexto.")
				return {"ok": False, "chat_id": chat_id, "reason": "usuario_nao_encontrado_reset"}

			new_thread_id = _new_thread_id(chat_id)
			Repository.usuarios.atualizar(db, usuario_db.id, telegram_thread_id=new_thread_id)
			_log_info(f"Contexto reiniciado - user_id={usuario.id}, new_thread_id={new_thread_id}")

		send_message(
			chat_id,
			"Contexto da conversa reiniciado com sucesso. Vamos começar uma nova thread aqui.\n"
			"Se quiser, me diga seu próximo registro ou dúvida.",
		)
		return {
			"ok": True,
			"chat_id": chat_id,
			"reason": "contexto_reiniciado",
			"thread_id": new_thread_id,
		}

	# Migração lazy para usuários antigos sem thread persistida
	if not getattr(usuario, "telegram_thread_id", None):
		_log_info(f"Migrando usuário para thread persistida - user_id={usuario.id}, chat_id={chat_id}")
		with SessionLocal() as db:
			Repository.usuarios.atualizar(db, usuario.id, telegram_thread_id=str(chat_id))
		usuario.telegram_thread_id = str(chat_id)

	thread_id = _resolve_thread_id(usuario, chat_id)
	_log_info(f"Iniciando processamento - user_id={usuario.id}, chat_id={chat_id}, thread_id={thread_id}")

	config = {
		"configurable": {
			"thread_id": thread_id,
			"telegram_chat_id": str(chat_id),
			"telegram_message_thread_id": int(telegram_message_thread_id) if telegram_message_thread_id is not None else None,
			**_conversation_date_payload(),
			"actor_user_id": usuario.id,
			"actor_level": usuario.nivel_acesso.value if hasattr(usuario.nivel_acesso, "value") else str(usuario.nivel_acesso),
			"actor_name": usuario.nome,
			"actor_chat_display_name": chat_display_name,
		}
	}
	
	try:
		print(f"[TELEGRAM] Invocando graph com mensagem: {text[:50]}...", flush=True)
		logger.debug(f"[TELEGRAM] Invocando graph com mensagem: {text[:50]}...")
		response = graph.invoke({"messages": [HumanMessage(content=text)]}, config)
		print(f"[TELEGRAM] Graph retornou resposta. Tipo: {type(response)}", flush=True)
		logger.debug(f"[TELEGRAM] Graph retornou resposta. Tipo: {type(response)}")
	except Exception as e:
		print(f"[TELEGRAM] ERRO ao invocar graph - chat_id={chat_id}: {e}", flush=True)
		logger.error(f"[TELEGRAM] ERRO ao invocar graph - chat_id={chat_id}: {e}", exc_info=True)
		send_message(chat_id, "Desculpa, ocorreu um erro ao processar sua mensagem. Tente novamente.")
		return {"ok": False, "chat_id": chat_id, "reason": "erro_graph", "error": str(e)}
	
	try:
		response_messages = response.get("messages", [])
		print(f"[TELEGRAM] Mensagens na resposta: {len(response_messages)}", flush=True)
		logger.debug(f"[TELEGRAM] Mensagens na resposta: {len(response_messages)}")
		
		if not response_messages:
			print(f"[TELEGRAM] AVISO: response_messages vazio - chat_id={chat_id}", flush=True)
			logger.warning(f"[TELEGRAM] AVISO: response_messages vazio - chat_id={chat_id}")
			send_message(chat_id, "Recebi sua mensagem, mas não consegui gerar uma resposta.")
			return {"ok": True, "chat_id": chat_id}
		
		ui_dispatched = _response_used_telegram_ui(response_messages)
		print(f"[TELEGRAM] UI Dispatched: {ui_dispatched}", flush=True)
		logger.info(f"[TELEGRAM] UI Dispatched: {ui_dispatched}")
		
		reply = _extract_text_content(response_messages[-1].content)
		logger.debug(f"[TELEGRAM] Texto extraído (primeiro 100 chars): {reply[:100] if reply else 'VAZIO'}")
		
		if not reply:
			print(f"[TELEGRAM] AVISO: Nenhuma resposta em texto gerada - chat_id={chat_id}, ui_dispatched={ui_dispatched}", flush=True)
			logger.warning(f"[TELEGRAM] AVISO: Nenhuma resposta em texto gerada - chat_id={chat_id}, ui_dispatched={ui_dispatched}")
			reply = "Recebi sua mensagem, mas não consegui gerar uma resposta em texto."
		
		if not ui_dispatched:
			_log_info(f"Enviando resposta via Telegram - chat_id={chat_id}, tamanho={len(reply)}")
			try:
				send_message(chat_id, reply)
				_log_info(f"Mensagem enviada com sucesso - chat_id={chat_id}")
			except Exception as e:
				_log_error(f"ERRO ao enviar mensagem - chat_id={chat_id}: {e}", exc_info=True)
				return {"ok": False, "chat_id": chat_id, "reason": "erro_envio", "error": str(e)}
		else:
			_log_info(f"Resposta via UI dispensada (ui_dispatched=True) - chat_id={chat_id}")
		
		return {"ok": True, "chat_id": chat_id}
		
	except Exception as e:
		_log_error(f"ERRO ao processar resposta do graph - chat_id={chat_id}: {e}", exc_info=True)
		try:
			send_message(chat_id, "Desculpa, ocorreu um erro ao processar sua mensagem. Tente novamente.")
		except Exception as send_error:
			logger.error(f"[TELEGRAM] Falha ao enviar mensagem de erro - chat_id={chat_id}: {send_error}")
		return {"ok": False, "chat_id": chat_id, "reason": "erro_resposta", "error": str(e)}

def start_polling() -> None:
	"""Inicia polling do Telegram usando async."""
	global _POLLING_STARTED

	with _POLLING_LOCK:
		if _POLLING_STARTED:
			logger.info("Polling do Telegram já está ativo neste processo. Ignorando nova inicialização.")
			return
		_POLLING_STARTED = True

	logger.info("Iniciando polling do Telegram...")
	logger.info("Verifique se TELEGRAM_TOKEN está correto no .env")
	
	try:
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		loop.run_until_complete(_start_polling_async())
	except KeyboardInterrupt:
		logger.info("Polling encerrado pelo usuário.")
	except Exception as e:
		logger.error(f"Erro fatal no polling: {e}")
	finally:
		loop.close()


async def _start_polling_async() -> None:
	"""Polling assíncrono com melhor tratamento de erros e reconexão."""
	offset = None
	consecutive_errors = 0
	max_consecutive_errors = 5
	
	while True:
		try:
			# Tenta buscar updates com timeout
			updates = await get_updates_async(offset)
			consecutive_errors = 0  # Reset contador após sucesso
			
			for update in updates:
				try:
					handle_telegram_update(update)
					offset = update.get("update_id", 0) + 1
				except Exception as e:
					logger.error(f"Erro ao processar update: {e}", exc_info=True)
			
			# Pequeno delay para evitar CPU 100%
			if not updates:
				await asyncio.sleep(0.5)
				
		except RuntimeError as e:
			consecutive_errors += 1
			wait = min(2 ** consecutive_errors, 60)  # Max 60 segundos
			logger.warning(f"Erro ao buscar updates ({consecutive_errors}/{max_consecutive_errors}): {e}. Aguardando {wait}s...")
			
			if consecutive_errors >= max_consecutive_errors:
				logger.error(f"Muitos erros consecutivos ({consecutive_errors}). Encerrando polling.")
				raise
			
			await asyncio.sleep(wait)
		except asyncio.CancelledError:
			logger.info("Polling cancelado.")
			break
		except Exception as e:
			logger.error(f"Erro inesperado no polling: {e}", exc_info=True)
			raise
