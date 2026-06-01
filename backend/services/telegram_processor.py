"""Message batch processor.

Single responsibility: given a list of Telegram updates for the same chat,
extract text, resolve the user, run the agent, and send the reply.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime

from langchain_core.messages import HumanMessage

try:
    from backend.agents.graph import graph
except ImportError:
    from agents.graph import graph  # type: ignore[no-redef]

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
from backend.agents.session_service import get_or_create_conversa, atualizar_ultima_mensagem

logger = logging.getLogger(__name__)

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
        raw_source_id = str(raw_messages[-1].id) if raw_messages else None
        logger.info(
            "Iniciando processamento - user_id=%d, chat_id=%s, thread_id=%s, batch=%d",
            usuario.id, chat_id, thread_id, len(extracted),
        )

        # Resolve ou cria a sessão de conversa e determina a obra ativa do usuário
        tenant_id = getattr(usuario, "tenant_id", None)
        conversa_id = None
        obra_id_ativa = None
        try:
            from backend.core.config import get_ambiente
            _t_conversa = time.monotonic()
            with SessionLocal() as db:
                tenant_id = _resolver_tenant_ativo(db, usuario)
                conversa = get_or_create_conversa(
                    db, usuario.id, tenant_id, str(chat_id), thread_id,
                    ambiente=get_ambiente(),
                )
                conversa_id = conversa.id
                if tenant_id is not None:
                    obra_id_ativa = _resolver_obra_ativa(db, usuario.id, tenant_id)
            logger.info("[TIMING] get_or_create_conversa=%.2fs - chat_id=%s", time.monotonic() - _t_conversa, chat_id)
        except Exception as exc:
            logger.warning("Falha ao obter/criar conversa: %s", exc)

        actor_level_str = (
            usuario.nivel_acesso.value
            if hasattr(usuario.nivel_acesso, "value")
            else str(usuario.nivel_acesso)
        )
        config = {
            "configurable": {
                "thread_id": thread_id,
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

        # Pré-constrói contexto caro UMA vez antes do graph.invoke().
        # _build_system_message é chamado em cada node do router loop —
        # sem esse cache, build_tenant_snapshot + embeddings rodam N vezes.
        _t_ctx = time.monotonic()
        try:
            from backend.agents.context.vector_context import get_context_for_query
            from backend.agents.context.tenant_snapshot import build_tenant_snapshot
            from backend.agents.session_service import buscar_memorias_relevantes

            prebuilt_vector_ctx = get_context_for_query(batched_text)

            prebuilt_snapshot = ""
            prebuilt_memories = ""
            if tenant_id is not None:
                with SessionLocal() as ctx_db:
                    prebuilt_snapshot = build_tenant_snapshot(
                        ctx_db, tenant_id, obra_id_ativa, actor_level_str
                    )
                    if batched_text:
                        mems = buscar_memorias_relevantes(ctx_db, tenant_id, batched_text)
                        if mems:
                            prebuilt_memories = (
                                "\n\nMemórias de conversas anteriores relevantes:\n"
                                + "\n---\n".join(mems)
                            )

            config["configurable"]["_prebuilt_vector_ctx"] = prebuilt_vector_ctx
            config["configurable"]["_prebuilt_snapshot"] = prebuilt_snapshot
            config["configurable"]["_prebuilt_memories"] = prebuilt_memories
            logger.info("[TIMING] prebuilt context=%.2fs - chat_id=%s", time.monotonic() - _t_ctx, chat_id)
        except Exception as exc:
            logger.warning("Falha ao pré-construir contexto: %s — continuando sem cache.", exc)

        typing_stop = self._typing.start(chat_id=chat_id, message_thread_id=thread_hint)
        _t_agent = time.monotonic()
        try:
            result = self._invoke_agent(batched_text, config, chat_id, raw_messages)
        finally:
            typing_stop()
        logger.info("[TIMING] _invoke_agent total=%.1fs - chat_id=%s", time.monotonic() - _t_agent, chat_id)

        # Stamp the session with the last message text (for future memory recall)
        if conversa_id is not None:
            try:
                _t_mem = time.monotonic()
                with SessionLocal() as db:
                    atualizar_ultima_mensagem(db, conversa_id, batched_text)
                logger.info("[TIMING] atualizar_ultima_mensagem=%.2fs - chat_id=%s", time.monotonic() - _t_mem, chat_id)
            except Exception as exc:
                logger.warning("Falha ao atualizar ultima_msg_em: %s", exc)

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
        """Retry once on stale-connection errors; the pool replaces the bad connection automatically."""
        import psycopg
        t0 = time.monotonic()
        for attempt in range(2):
            try:
                result = graph.invoke({"messages": [HumanMessage(content=text)]}, invoke_config)
                elapsed = time.monotonic() - t0
                logger.info("[TIMING] graph.invoke() concluído em %.1fs - chat_id=%s", elapsed, chat_id)
                return result
            except psycopg.OperationalError as exc:
                if attempt == 0:
                    logger.warning(
                        "[TIMING] graph.invoke() falhou com OperationalError após %.1fs, retentando - chat_id=%s: %s",
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
                    logger.warning("Graph atingiu recursion_limit - chat_id=%s", chat_id)
                    persistence.mark_error(raw_messages, "recursion_limit")
                    self._send_reply(
                        chat_id,
                        "⚠️ Sua solicitação ficou complexa demais. Tente dividir em partes menores.",
                    )
                    return {"ok": False, "chat_id": chat_id, "reason": "recursion_limit"}
            except ImportError:
                pass
            logger.error("Erro ao invocar graph - chat_id=%s: %s", chat_id, exc, exc_info=True)
            persistence.mark_error(raw_messages, str(exc))
            self._send_reply(
                chat_id, "Desculpa, ocorreu um erro ao processar sua mensagem. Tente novamente."
            )
            return {"ok": False, "chat_id": chat_id, "reason": "erro_graph", "error": str(exc)}

        msgs = response.get("messages", [])
        if not msgs:
            self._send_reply(
                chat_id, "Recebi suas mensagens, mas não consegui gerar uma resposta."
            )
            persistence.mark_processed(raw_messages)
            return {"ok": True, "chat_id": chat_id}

        reply = (
            extract_text_content(msgs[-1].content)
            or "Recebi suas mensagens, mas não consegui gerar uma resposta em texto."
        )

        if not response_used_telegram_ui(msgs):
            try:
                self._send_reply(chat_id, reply)
            except Exception as exc:
                logger.error(
                    "Erro ao enviar mensagem - chat_id=%s: %s", chat_id, exc, exc_info=True
                )
                persistence.mark_error(raw_messages, f"erro_envio: {exc}")
                return {"ok": False, "chat_id": chat_id, "reason": "erro_envio", "error": str(exc)}

        persistence.mark_processed(raw_messages)
        return {"ok": True, "chat_id": chat_id}
