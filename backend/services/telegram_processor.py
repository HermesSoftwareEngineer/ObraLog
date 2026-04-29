"""Message batch processor.

Single responsibility: given a list of Telegram updates for the same chat,
extract text, resolve the user, run the agent, and send the reply.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from langchain_core.messages import HumanMessage

try:
    from backend.agents.graph import graph
except ImportError:
    from agents.graph import graph  # type: ignore[no-redef]

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

logger = logging.getLogger(__name__)

_RESET_COMMANDS = {
    "/nova_thread", "/novathread", "/reset_contexto",
    "/reset", "/limpar_contexto", "/zerar_contexto",
}


def _is_reset_command(text: str) -> bool:
    return text.strip().lower() in _RESET_COMMANDS


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

        config = {
            "configurable": {
                "thread_id": thread_id,
                "telegram_chat_id": str(chat_id),
                "telegram_message_thread_id": int(thread_hint) if thread_hint is not None else None,
                "source_message_id": raw_source_id,
                **_conversation_date_payload(),
                "actor_user_id": usuario.id,
                "actor_level": (
                    usuario.nivel_acesso.value
                    if hasattr(usuario.nivel_acesso, "value")
                    else str(usuario.nivel_acesso)
                ),
                "actor_name": usuario.nome,
                "actor_chat_display_name": display_name,
            }
        }

        typing_stop = self._typing.start(chat_id=chat_id, message_thread_id=thread_hint)
        try:
            return self._invoke_agent(
                _build_batched_text(extracted), config, chat_id, raw_messages
            )
        finally:
            typing_stop()

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

    def _invoke_agent(
        self, text: str, config: dict, chat_id, raw_messages: list
    ) -> dict:
        try:
            response = graph.invoke({"messages": [HumanMessage(content=text)]}, config)
        except Exception as exc:
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
