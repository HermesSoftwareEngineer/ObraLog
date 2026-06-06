"""Message batch processor.

Single responsibility: given a list of Telegram updates for the same chat,
extract text, resolve the user, run the agent, and send the reply.
"""
print("[BOOT] telegram_processor.py: módulo carregando...", flush=True)

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime

print("[BOOT] telegram_processor.py: importando langchain_core...", flush=True)
from langchain_core.messages import HumanMessage
print("[BOOT] telegram_processor.py: langchain_core OK", flush=True)

print("[BOOT] telegram_processor.py: importando agents.graph (PESADO — inicia checkpointer)...", flush=True)
try:
    from backend.agents.graph import graph
except ImportError:
    from agents.graph import graph  # type: ignore[no-redef]
print("[BOOT] telegram_processor.py: agents.graph OK", flush=True)

print("[BOOT] telegram_processor.py: importando db/services...", flush=True)
from backend.db.models import UsuarioObra
from backend.db.repository import Repository
from backend.db.session import SessionLocal
from backend.services.telegram_client import BotClient
from backend.services.telegram_typing import TypingIndicator
from backend.services.telegram_extractor import (
    MessageExtractor,
    extract_text_content,
    response_used_telegram_ui,
)
from backend.services import telegram_persistence as persistence
from backend.services.telegram_linker import UserLinker
from backend.agents.session_service import (
    get_or_create_conversa,
    atualizar_ultima_mensagem,
)
from backend.agents.context.tenant_snapshot import build_tenant_snapshot
from backend.agents.instructions_store import read_agent_instructions

logger = logging.getLogger(__name__)

# Timeout máximo para graph.invoke(). Se o LLM travar além desse limite, o job
# falha com erro claro em vez de bloquear a thread do worker indefinidamente.
_AGENT_INVOKE_TIMEOUT = float(os.environ.get("AGENT_INVOKE_TIMEOUT_SECONDS", "120.0"))

# Prefixo de ambiente para isolar checkpoints LangGraph entre dev e prod.
# Dev e prod apontam pro mesmo Supabase — sem esse prefixo disputam o mesmo
# lock de checkpoint para o mesmo thread_id, causando hang de centenas de segundos.
_OBRALOG_ENV = os.environ.get("OBRALOG_ENV", "prod")


def _scoped_thread_id(thread_id: str) -> str:
    """Prefixa thread_id com o ambiente para evitar conflito de lock no checkpointer."""
    prefix = f"{_OBRALOG_ENV}:"
    return thread_id if thread_id.startswith(prefix) else f"{prefix}{thread_id}"

# Cache do prebuilt context por thread_id.
# Gerado UMA VEZ na primeira mensagem da thread; reutilizado em todas as seguintes.
# /reset cria novo thread_id → cache invalidado automaticamente.
_ctx_cache: OrderedDict[str, dict] = OrderedDict()
_ctx_cache_lock = threading.Lock()
_CTX_CACHE_MAX = 200


def _cache_get(thread_id: str) -> dict | None:
    with _ctx_cache_lock:
        entry = _ctx_cache.get(thread_id)
        if entry is not None:
            _ctx_cache.move_to_end(thread_id)
        return entry


def _cache_set(thread_id: str, ctx: dict) -> None:
    with _ctx_cache_lock:
        _ctx_cache[thread_id] = ctx
        _ctx_cache.move_to_end(thread_id)
        while len(_ctx_cache) > _CTX_CACHE_MAX:
            _ctx_cache.popitem(last=False)

_RESET_COMMANDS = {
    "/nova_thread", "/novathread", "/reset_contexto",
    "/reset", "/limpar_contexto", "/zerar_contexto",
}


def _is_reset_command(text: str) -> bool:
    return text.strip().lower() in _RESET_COMMANDS


def _resolver_tenant_ativo(db, usuario) -> int | None:
    """Para admins, usa o tenant marcado como padrão em usuario_tenants.
    Fallback: usuario.tenant_id (comportamento original para não-admins).
    """
    nivel = (
        usuario.nivel_acesso.value
        if hasattr(usuario.nivel_acesso, "value")
        else str(usuario.nivel_acesso)
    )
    if nivel == "administrador":
        tenant_id = Repository.usuario_tenants.obter_tenant_padrao(db, usuario.id)
        if tenant_id is not None:
            return tenant_id
    return getattr(usuario, "tenant_id", None)


def _resolver_obra_ativa(db, usuario_id: int, tenant_id: int) -> int | None:
    """Resolve a obra ativa do usuário automaticamente quando possível.

    - 1 obra: usa diretamente.
    - Várias obras com uma marcada como padrão: usa a padrão.
    - Várias obras sem padrão: retorna None — agente pergunta ao usuário.
    """
    obras = (
        db.query(UsuarioObra)
        .filter(
            UsuarioObra.usuario_id == usuario_id,
            UsuarioObra.tenant_id == tenant_id,
            UsuarioObra.ativo.is_(True),
        )
        .all()
    )
    if len(obras) == 1:
        return obras[0].obra_id
    padrao = next((o for o in obras if o.eh_padrao), None)
    if padrao:
        return padrao.obra_id
    return None


def _new_thread_id(chat_id) -> str:
    return f"{chat_id}:{uuid.uuid4().hex}"


def _resolve_thread_id(usuario, chat_id) -> str:
    stored = getattr(usuario, "telegram_thread_id", None)
    if isinstance(stored, str) and stored.strip():
        return stored
    return str(chat_id)


def _conversation_date_payload() -> dict:
    now = datetime.now()
    return {
        "conversation_date": now.date().isoformat(),
        "conversation_date_br": now.strftime("%d/%m/%Y"),
    }


def _build_batched_text(entries: list[str]) -> str:
    if len(entries) == 1:
        return entries[0]
    parts = [
        "Recebi uma sequência de mensagens em pouco tempo. Considere tudo junto no mesmo contexto:"
    ]
    for i, item in enumerate(entries, 1):
        parts.append(f"{i}. {item}")
    return "\n".join(parts)


class MessageProcessor:
    """Processes a batch of Telegram updates through the LangGraph agent."""

    def __init__(self, client: BotClient) -> None:
        self._client = client
        self._extractor = MessageExtractor(client)
        self._typing = TypingIndicator(client)
        self._linker = UserLinker(client)

    def _send_reply(self, chat_id, reply: str) -> None:
        """Send and persist an agent response message."""
        if not reply:
            return
        result = self._client.send_message(chat_id, reply)
        if result and result.get("message_id"):
            try:
                with SessionLocal() as db:
                    Repository.mensagens_campo.criar_agent_response(
                        db,
                        telegram_chat_id=str(chat_id),
                        telegram_message_id=result["message_id"],
                        texto=reply,
                    )
            except Exception as exc:
                logger.warning(
                    "Falha ao persistir resposta do agente para chat_id=%s: %s",
                    chat_id,
                    exc,
                )

    def process(self, updates: list[dict]) -> dict:
        if not updates:
            return {"ok": True, "ignored": True, "reason": "batch_vazio"}

        first_msg = updates[0].get("message") or updates[0].get("edited_message") or {}
        first_chat = first_msg.get("chat") or {}
        chat_id = first_chat.get("id")
        if chat_id is None:
            raise RuntimeError("Chat inválido no batch.")

        display_name = (
            first_chat.get("first_name") or first_chat.get("username") or str(chat_id)
        )
        thread_hint = first_msg.get("message_thread_id")

        # Extract text from each update
        extracted: list[str] = []
        raw_messages = []
        for update in updates:
            message = update.get("message")
            if not message:
                continue
            if message.get("message_thread_id") is not None:
                thread_hint = message["message_thread_id"]
            text = self._extractor.extract(message, chat_id)
            if not text:
                continue
            extracted.append(text)
            raw_messages.append(
                persistence.persist(
                    update=update, message=message, chat_id=chat_id,
                    texto_extraido=text, usuario_id=None,
                )
            )

        if not extracted:
            return {"ok": True, "ignored": True, "reason": "batch_sem_texto"}

        logger.info("Processando batch - chat_id=%s, mensagens=%d", chat_id, len(extracted))

        usuario = self._linker.get_user(chat_id)
        if not usuario:
            logger.warning("Usuário não vinculado - chat_id=%s", chat_id)
            return self._linker.handle_unlinked(chat_id, extracted, raw_messages)

        if any(_is_reset_command(e) for e in extracted):
            return self._handle_reset(chat_id, usuario, raw_messages)

        persistence.set_user(raw_messages, usuario.id)

        if not getattr(usuario, "telegram_thread_id", None):
            with SessionLocal() as db:
                Repository.usuarios.atualizar(db, usuario.id, telegram_thread_id=str(chat_id))
            usuario.telegram_thread_id = str(chat_id)

        thread_id = _resolve_thread_id(usuario, chat_id)
        scoped_tid = _scoped_thread_id(thread_id)
        raw_source_id = str(raw_messages[-1].id) if raw_messages else None
        logger.info(
            "Iniciando processamento - user_id=%d, chat_id=%s, thread_id=%s, batch=%d",
            usuario.id, chat_id, scoped_tid, len(extracted),
        )

        # Resolve conversa, obra ativa e prebuilt context numa única sessão DB.
        # Evita abrir 2 conexões separadas ao Supabase (cada abertura custa ~2-3s em prod).
        tenant_id = getattr(usuario, "tenant_id", None)
        conversa_id = None
        obra_id_ativa = None
        actor_level_str = (
            usuario.nivel_acesso.value
            if hasattr(usuario.nivel_acesso, "value")
            else str(usuario.nivel_acesso)
        )

        cached_ctx = _cache_get(scoped_tid)

        _t_db = time.monotonic()
        try:
            from backend.core.config import get_ambiente
            with SessionLocal() as db:
                tenant_id = _resolver_tenant_ativo(db, usuario)
                conversa = get_or_create_conversa(
                    db, usuario.id, tenant_id, str(chat_id), thread_id,
                    ambiente=get_ambiente(),
                )
                conversa_id = conversa.id
                if tenant_id is not None:
                    obra_id_ativa = _resolver_obra_ativa(db, usuario.id, tenant_id)

                if cached_ctx is None and tenant_id is not None:
                    prebuilt_snapshot = build_tenant_snapshot(
                        db, tenant_id, obra_id_ativa, actor_level_str
                    )
                else:
                    prebuilt_snapshot = ""
            logger.info("[TIMING] db_setup=%.2fs - chat_id=%s", time.monotonic() - _t_db, chat_id)
        except Exception as exc:
            logger.warning("Falha ao preparar contexto DB: %s", exc)
            prebuilt_snapshot = ""

        config = {
            "configurable": {
                "thread_id": scoped_tid,
                "telegram_chat_id": str(chat_id),
                "telegram_message_thread_id": int(thread_hint) if thread_hint is not None else None,
                "source_message_id": raw_source_id,
                **_conversation_date_payload(),
                "actor_user_id": usuario.id,
                "tenant_id": tenant_id,
                "conversa_id": conversa_id,
                "actor_level": actor_level_str,
                "actor_name": usuario.nome,
                "actor_chat_display_name": display_name,
                "obra_id_ativa": obra_id_ativa,
            }
        }

        batched_text = _build_batched_text(extracted)

        # Prebuilt context: gerado UMA VEZ por thread e cacheado em memória.
        # Nas mensagens seguintes da mesma thread o cache é usado diretamente — zero DB.
        # /reset cria novo thread_id → cache invalidado automaticamente.
        if cached_ctx is not None:
            config["configurable"].update(cached_ctx)
            logger.info("Prebuilt context (cache hit) - chat_id=%s thread_id=%s", chat_id, scoped_tid)
        else:
            _t_ctx = time.monotonic()
            try:
                built_ctx = {
                    "_prebuilt_vector_ctx": read_agent_instructions(),
                    "_prebuilt_snapshot":   prebuilt_snapshot,
                    "_prebuilt_memories":   "",
                }
                config["configurable"].update(built_ctx)
                _cache_set(scoped_tid, built_ctx)
                logger.info(
                    "[TIMING] prebuilt context (cache miss) =%.2fs - chat_id=%s",
                    time.monotonic() - _t_ctx, chat_id,
                )
            except Exception as exc:
                logger.warning("Falha ao pré-construir contexto: %s — continuando sem cache.", exc)

        typing_stop = self._typing.start(chat_id=chat_id, message_thread_id=thread_hint)
        _t_agent = time.monotonic()
        try:
            result = self._invoke_agent(batched_text, config, chat_id, raw_messages)
        finally:
            typing_stop()
        logger.info("[TIMING] _invoke_agent total=%.1fs - chat_id=%s", time.monotonic() - _t_agent, chat_id)

        # Atualiza ultima_msg_em da conversa em background (sem embedding — MEMORY_ENABLED=false).
        if conversa_id is not None:
            _captured_text = batched_text
            _captured_id   = conversa_id

            def _update_conversa_bg() -> None:
                try:
                    with SessionLocal() as _db:
                        atualizar_ultima_mensagem(_db, _captured_id, _captured_text)
                except Exception as exc:
                    logger.warning("Falha ao atualizar conversa %s em background: %s", _captured_id, exc)

            threading.Thread(
                target=_update_conversa_bg,
                daemon=True,
                name=f"update-conversa-{conversa_id}",
            ).start()

        return result

    def _handle_reset(self, chat_id, usuario, raw_messages: list) -> dict:
        logger.info("Reset de contexto - chat_id=%s, user_id=%d", chat_id, usuario.id)
        with SessionLocal() as db:
            u = Repository.usuarios.obter_por_id(db, usuario.id)
            if not u:
                persistence.mark_error(raw_messages, "usuario_nao_encontrado_reset")
                self._send_reply(
                    chat_id, "Não encontrei seu usuário para reiniciar o contexto."
                )
                return {"ok": False, "chat_id": chat_id, "reason": "usuario_nao_encontrado_reset"}
            new_tid = _new_thread_id(chat_id)
            Repository.usuarios.atualizar(db, u.id, telegram_thread_id=new_tid)

        persistence.set_user(raw_messages, usuario.id)
        persistence.mark_processed(raw_messages)
        self._send_reply(
            chat_id,
            "Contexto da conversa reiniciado com sucesso. Vamos começar uma nova thread aqui.\n"
            "Se quiser, me diga seu próximo registro ou dúvida.",
        )
        return {"ok": True, "chat_id": chat_id, "reason": "contexto_reiniciado", "thread_id": new_tid}

    def _invoke_with_retry(self, text: str, invoke_config: dict, chat_id) -> dict:
        """Invoke the graph with timeout + retry on stale-connection errors.

        Timeout evita que um LLM travado bloqueie a thread do worker por 10+ minutos.
        A thread interna continua em background até o LLM responder ou falhar por conta própria.
        """
        import psycopg
        from backend.agents.nodes._tool_utils import resolve_tool_map

        # Pré-computa o tool_map AQUI, no thread do request handler (fora de qualquer
        # run_until_complete). Dentro do graph.invoke() o @tool/Pydantic interage com
        # o event loop de forma que trava por 70-200s. Pré-computar e injetar no config
        # evita que agent_node precise reconstruir os schemas.
        _t_pre = time.monotonic()
        pre_tool_map = resolve_tool_map(invoke_config)
        logger.info("[PASSO] pre_tool_map=%.2fs tools=%d - chat_id=%s",
                    time.monotonic() - _t_pre, len(pre_tool_map), chat_id)
        invoke_config = {
            **invoke_config,
            "configurable": {
                **invoke_config.get("configurable", {}),
                "_pre_tool_map": pre_tool_map,
            },
        }

        t0 = time.monotonic()
        for attempt in range(2):
            try:
                result_holder: list = [None]
                exc_holder: list = [None]

                def _run_graph() -> None:
                    try:
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            import nest_asyncio
                            nest_asyncio.apply(loop)
                        except ImportError:
                            pass
                        try:
                            result_holder[0] = graph.invoke(
                                {"messages": [HumanMessage(content=text)]}, invoke_config
                            )
                        finally:
                            loop.close()
                    except Exception as exc:  # noqa: BLE001
                        exc_holder[0] = exc

                t = threading.Thread(target=_run_graph, daemon=True, name=f"graph-invoke-{chat_id}")
                logger.info("[PASSO] graph.invoke() iniciado - chat_id=%s attempt=%d", chat_id, attempt + 1)
                t.start()
                t.join(timeout=_AGENT_INVOKE_TIMEOUT)

                if t.is_alive():
                    elapsed = time.monotonic() - t0
                    logger.error(
                        "[PASSO] graph.invoke() TIMEOUT após %.0fs - chat_id=%s "
                        "(thread continua em background até o LLM responder)",
                        elapsed, chat_id,
                    )
                    raise TimeoutError(
                        f"graph.invoke() excedeu {_AGENT_INVOKE_TIMEOUT:.0f}s — "
                        "LLM provavelmente travado ou com latência anormal"
                    )

                if exc_holder[0] is not None:
                    logger.error(
                        "[PASSO] graph.invoke() falhou com exceção em %.1fs - chat_id=%s: %s",
                        time.monotonic() - t0, chat_id, exc_holder[0],
                    )
                    raise exc_holder[0]

                elapsed = time.monotonic() - t0
                logger.info("[PASSO] graph.invoke() concluído em %.1fs - chat_id=%s", elapsed, chat_id)
                return result_holder[0]

            except TimeoutError:
                raise  # Não tenta novamente em timeout — o LLM já está ocupado
            except psycopg.OperationalError as exc:
                if attempt == 0:
                    logger.warning(
                        "[PASSO] graph.invoke() OperationalError em %.1fs, retentando - chat_id=%s: %s",
                        time.monotonic() - t0, chat_id, exc,
                    )
                    time.sleep(0.5)
                    continue
                raise

    def _invoke_agent(
        self, text: str, config: dict, chat_id, raw_messages: list
    ) -> dict:
        invoke_config = {**config, "recursion_limit": 14}
        try:
            response = self._invoke_with_retry(text, invoke_config, chat_id)
        except Exception as exc:
            try:
                from langgraph.errors import GraphRecursionError
                if isinstance(exc, GraphRecursionError):
                    logger.warning("[PASSO] Graph atingiu recursion_limit - chat_id=%s", chat_id)
                    persistence.mark_error(raw_messages, "recursion_limit")
                    self._send_reply(
                        chat_id,
                        "⚠️ Sua solicitação ficou complexa demais. Tente dividir em partes menores.",
                    )
                    return {"ok": False, "chat_id": chat_id, "reason": "recursion_limit"}
            except ImportError:
                pass
            logger.error("[PASSO] Erro ao invocar graph - chat_id=%s: %s", chat_id, exc, exc_info=True)
            persistence.mark_error(raw_messages, str(exc))
            try:
                self._send_reply(
                    chat_id, "Desculpa, ocorreu um erro ao processar sua mensagem. Tente novamente."
                )
            except Exception as send_exc:
                logger.warning("[PASSO] Falha ao enviar mensagem de erro para chat_id=%s: %s", chat_id, send_exc)
            return {"ok": False, "chat_id": chat_id, "reason": "erro_graph", "error": str(exc)}

        logger.info("[PASSO] Extraindo resposta das mensagens do grafo - chat_id=%s", chat_id)
        msgs = response.get("messages", [])
        if not msgs:
            logger.warning("[PASSO] Grafo retornou sem mensagens - chat_id=%s", chat_id)
            self._send_reply(
                chat_id, "Recebi suas mensagens, mas não consegui gerar uma resposta."
            )
            persistence.mark_processed(raw_messages)
            return {"ok": True, "chat_id": chat_id}

        reply = (
            extract_text_content(msgs[-1].content)
            or "Recebi suas mensagens, mas não consegui gerar uma resposta em texto."
        )
        logger.info(
            "[PASSO] Resposta extraída (%d chars) - chat_id=%s usou_telegram_ui=%s",
            len(reply), chat_id, response_used_telegram_ui(msgs),
        )

        if not response_used_telegram_ui(msgs):
            _t_send = time.monotonic()
            logger.info("[PASSO] Enviando resposta ao Telegram - chat_id=%s", chat_id)
            try:
                self._send_reply(chat_id, reply)
                logger.info(
                    "[PASSO] Resposta enviada em %.1fs - chat_id=%s",
                    time.monotonic() - _t_send, chat_id,
                )
            except Exception as exc:
                logger.error(
                    "[PASSO] Erro ao enviar mensagem em %.1fs - chat_id=%s: %s",
                    time.monotonic() - _t_send, chat_id, exc, exc_info=True,
                )
                persistence.mark_error(raw_messages, f"erro_envio: {exc}")
                return {"ok": False, "chat_id": chat_id, "reason": "erro_envio", "error": str(exc)}

        logger.info("[PASSO] Marcando mensagens como processadas - chat_id=%s", chat_id)
        _t_persist = time.monotonic()
        persistence.mark_processed(raw_messages)
        logger.info(
            "[PASSO] Persistência concluída em %.2fs - chat_id=%s",
            time.monotonic() - _t_persist, chat_id,
        )
        return {"ok": True, "chat_id": chat_id}
