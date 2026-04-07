import json
import os
import time
import threading
import re
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from langchain_core.messages import HumanMessage

try:
	from backend.agents.graph import graph
except ImportError:
	from agents.graph import graph

from backend.db.repository import Repository
from backend.db.session import SessionLocal
from backend.agents.llms import transcribe_audio_bytes


_POLLING_LOCK = threading.Lock()
_POLLING_STARTED = False


def _telegram_api_call(method: str, params: dict, retries: int = 3) -> dict:
	token = os.environ.get("TELEGRAM_TOKEN")
	if not token:
		raise RuntimeError("TELEGRAM_TOKEN não configurado.")

	url = f"https://api.telegram.org/bot{token}/{method}"
	payload = json.dumps(params).encode("utf-8")
	request = Request(url, data=payload, headers={"Content-Type": "application/json"})

	for attempt in range(retries):
		try:
			with urlopen(request, timeout=60) as response:
				return json.loads(response.read().decode("utf-8"))
		except (HTTPError, URLError) as exc:
			if attempt == retries - 1:
				raise RuntimeError("Erro na API do Telegram.") from exc
			wait = 2 ** attempt
			print(f"Erro ao conectar ({attempt + 1}/{retries}), aguardando {wait}s...")
			time.sleep(wait)
		except TimeoutError as exc:
			if attempt == retries - 1:
				raise RuntimeError("Timeout na API do Telegram após múltiplas tentativas.") from exc
			wait = 2 ** attempt
			print(f"Timeout ({attempt + 1}/{retries}), aguardando {wait}s...")
			time.sleep(wait)


def send_message(chat_id: int | str, text: str) -> None:
	_telegram_api_call("sendMessage", {"chat_id": chat_id, "text": text})


def set_webhook(base_url: str) -> None:
	if not base_url:
		raise RuntimeError("PUBLIC_BASE_URL não configurada para registrar webhook.")

	webhook_url = f"{base_url.rstrip('/')}/telegram/webhook"
	secret_token = os.environ.get("TELEGRAM_WEBHOOK_SECRET_TOKEN")
	print(f"Configurando webhook do Telegram para: {webhook_url}")
	payload = {"url": webhook_url}
	if secret_token:
		payload["secret_token"] = secret_token
	_telegram_api_call("setWebhook", payload)


def _extract_text_content(content) -> str:
	if isinstance(content, str):
		return content

	if isinstance(content, list):
		parts = []
		for item in content:
			if isinstance(item, str):
				parts.append(item)
			elif isinstance(item, dict):
				text_value = item.get("text")
				if isinstance(text_value, str):
					parts.append(text_value)
		return "\n".join(part for part in parts if part).strip()

	if isinstance(content, dict):
		text_value = content.get("text")
		if isinstance(text_value, str):
			return text_value

	return str(content)

def get_updates(offset: int | None = None) -> list:
	params = {"timeout": 30}
	if offset is not None:
		params["offset"] = offset
	result = _telegram_api_call("getUpdates", params)
	return result.get("result", [])


def _download_telegram_file(file_id: str) -> tuple[bytes, str]:
	token = os.environ.get("TELEGRAM_TOKEN")
	if not token:
		raise RuntimeError("TELEGRAM_TOKEN não configurado.")

	file_result = _telegram_api_call("getFile", {"file_id": file_id})
	file_info = file_result.get("result") or {}
	file_path = file_info.get("file_path")
	if not file_path:
		raise RuntimeError("Não foi possível obter o caminho do arquivo de áudio no Telegram.")

	file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
	with urlopen(file_url, timeout=60) as response:
		audio_bytes = response.read()

	mime_type = "audio/ogg"
	if file_path.endswith(".mp3"):
		mime_type = "audio/mpeg"
	elif file_path.endswith(".wav"):
		mime_type = "audio/wav"
	elif file_path.endswith(".m4a"):
		mime_type = "audio/mp4"

	return audio_bytes, mime_type


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

		file_result = _telegram_api_call("getFile", {"file_id": file_id})
		file_info = file_result.get("result") or {}
		file_path = file_info.get("file_path")
		if not file_path:
			raise RuntimeError("Não foi possível obter file_path da imagem no Telegram.")

		image_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
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


def handle_telegram_update(update: dict) -> dict:
	message = update.get("message") or update.get("edited_message")
	if not message:
		return {"ok": True, "ignored": True}

	chat = message.get("chat") or {}
	chat_id = chat.get("id")
	if chat_id is None:
		raise RuntimeError("Chat inválido no update do Telegram.")

	chat_display_name = (
		chat.get("first_name")
		or chat.get("username")
		or str(chat_id)
	)

	text = _extract_message_text_or_transcription(message, chat_id)
	if not text:
		return {"ok": True, "ignored": True}

	with SessionLocal() as db:
		usuario = Repository.usuarios.obter_por_telegram_chat_id(db, str(chat_id))

	if not usuario:
		link_code = _extract_link_code(text)
		if link_code:
			with SessionLocal() as db:
				code_item = Repository.telegram_link_codes.obter_valido_por_codigo(db, link_code)
				if not code_item:
					send_message(chat_id, "Código inválido ou expirado. Peça um novo código ao administrador.")
					return {"ok": False, "chat_id": chat_id, "reason": "codigo_invalido"}

				target_user = Repository.usuarios.obter_por_id(db, code_item.user_id)
				if not target_user:
					send_message(chat_id, "Usuário do código não encontrado. Solicite um novo código.")
					return {"ok": False, "chat_id": chat_id, "reason": "usuario_codigo_inexistente"}

				existing_chat_user = Repository.usuarios.obter_por_telegram_chat_id(db, str(chat_id))
				if existing_chat_user and existing_chat_user.id != target_user.id:
					send_message(chat_id, "Este Telegram já está vinculado a outro usuário.")
					return {"ok": False, "chat_id": chat_id, "reason": "chat_ja_vinculado"}

				Repository.usuarios.atualizar(
					db,
					target_user.id,
					telegram_chat_id=str(chat_id),
					telegram_thread_id=str(chat_id),
				)
				Repository.telegram_link_codes.marcar_usado(db, code_item.id)

			send_message(chat_id, "Vínculo concluído com sucesso. Agora você já pode usar o assistente.")
			return {"ok": True, "chat_id": chat_id, "reason": "vinculado_por_codigo"}

		send_message(
			chat_id,
			"Seu usuário ainda não está vinculado no sistema. Peça ao administrador um código de vínculo e envie: /vincular SEU_CODIGO",
		)
		return {"ok": False, "chat_id": chat_id, "reason": "usuario_nao_vinculado"}

	if _is_reset_context_command(text):
		with SessionLocal() as db:
			usuario_db = Repository.usuarios.obter_por_id(db, usuario.id)
			if not usuario_db:
				send_message(chat_id, "Não encontrei seu usuário para reiniciar o contexto.")
				return {"ok": False, "chat_id": chat_id, "reason": "usuario_nao_encontrado_reset"}

			new_thread_id = _new_thread_id(chat_id)
			Repository.usuarios.atualizar(db, usuario_db.id, telegram_thread_id=new_thread_id)

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
		with SessionLocal() as db:
			Repository.usuarios.atualizar(db, usuario.id, telegram_thread_id=str(chat_id))
		usuario.telegram_thread_id = str(chat_id)

	config = {
		"configurable": {
			"thread_id": _resolve_thread_id(usuario, chat_id),
			"actor_user_id": usuario.id,
			"actor_level": usuario.nivel_acesso.value if hasattr(usuario.nivel_acesso, "value") else str(usuario.nivel_acesso),
			"actor_name": usuario.nome,
			"actor_chat_display_name": chat_display_name,
		}
	}
	response = graph.invoke({"messages": [HumanMessage(content=text)]}, config)
	reply = _extract_text_content(response["messages"][-1].content)
	if not reply:
		reply = "Recebi sua mensagem, mas não consegui gerar uma resposta em texto."
	send_message(chat_id, reply)
	return {"ok": True, "chat_id": chat_id}

def start_polling() -> None:
	global _POLLING_STARTED

	with _POLLING_LOCK:
		if _POLLING_STARTED:
			print("Polling do Telegram já está ativo neste processo. Ignorando nova inicialização.")
			return
		_POLLING_STARTED = True

	offset = None
	print("Iniciando polling do Telegram...")
	print("Verifique se TELEGRAM_TOKEN está correto no .env\n")
	try:
		while True:
			try:
				updates = get_updates(offset)
				for update in updates:
					try:
						handle_telegram_update(update)
					except Exception as e:
						print(f"Erro ao processar update: {e}")
					offset = update.get("update_id", 0) + 1
			except (RuntimeError, ConnectionError) as e:
				print(f"Erro ao buscar updates: {e}")
				time.sleep(5)
	except KeyboardInterrupt:
		print("\nPolling encerrado.")
