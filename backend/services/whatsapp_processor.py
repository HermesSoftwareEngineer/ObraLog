"""WhatsApp message batch processor.

Single responsibility: given a list of normalized WhatsApp message dicts for
the same phone number, extract text, resolve the user, run the LangGraph agent,
and send the reply. Mirrors telegram_processor.py structure.
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
from backend.services.whatsapp_client import WhatsAppClient
from backend.services.whatsapp_extractor import MessageExtractor, extract_text_content
from backend.services.whatsapp_linker import UserLinker
from backend.services import whatsapp_persistence as persistence
from backend.agents.gateway.location_profile import resolve_runtime_location_context
from backend.agents.session_service import get_or_create_conversa, atualizar_ultima_mensagem

logger = logging.getLogger(__name__)

_RESET_COMMANDS = {
    "/nova_thread", "/novathread", "/reset_contexto",
    "/reset", "/limpar_contexto", "/zerar_contexto",
}


def _is_reset_command(text: str) -> bool:
    return text.strip().lower() in _RESET_COMMANDS


def _new_thread_id(phone: str) -> str:
    return f"wa:{phone}:{uuid.uuid4().hex}"


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
    """Processes a batch of WhatsApp messages through the LangGraph agent."""

    def __init__(self, client: WhatsAppClient) -> None:
        self._client = client
        self._extractor = MessageExtractor(client)
        self._linker = UserLinker(client)

    def _send_reply(self, phone: str, reply: str) -> None:
        if not reply:
            return
        result = self._client.send_text_message(phone, reply)
        if result and result.get("message_id"):
            try:
                with SessionLocal() as db:
                    Repository.mensagens_campo.criar_agent_response_whatsapp(
                        db,
                        chat_id=f"wa:{phone}",
                        message_id=result["message_id"],
                        texto=reply,
                    )
            except Exception as exc:
                logger.warning("Falha ao persistir resposta WA para phone=%s: %s", phone, exc)

    def process(self, msg_infos: list[dict]) -> dict:
        if not msg_infos:
            return {"ok": True, "ignored": True, "reason": "batch_vazio"}

        first = msg_infos[0]
        phone = first["from_phone"]
        display_name = first.get("display_name", phone)

        # Mark as read (receipt indicator — closest WA has to typing)
        for m in msg_infos:
            if m.get("message_id"):
                self._client.mark_as_read(m["message_id"])

        # Extract text from each message in the batch
        extracted: list[str] = []
        raw_messages = []
        for msg_info in msg_infos:
            text = self._extractor.extract(msg_info)
            if not text:
                continue
            extracted.append(text)
            raw_messages.append(
                persistence.persist(
                    msg_info=msg_info, texto_extraido=text, usuario_id=None,
                )
            )

        if not extracted:
            return {"ok": True, "ignored": True, "reason": "batch_sem_texto"}

        logger.info("Processando WA batch - phone=%s, mensagens=%d", phone, len(extracted))

        usuario = self._linker.get_user(phone)
        if not usuario:
            logger.warning("Usuário WA não vinculado - phone=%s", phone)
            return self._linker.handle_unlinked(phone, extracted, raw_messages)

        if any(_is_reset_command(e) for e in extracted):
            return self._handle_reset(phone, usuario, raw_messages)

        persistence.set_user(raw_messages, usuario.id)

        wa_chat_id = f"wa:{phone}"
        if not getattr(usuario, "telegram_thread_id", None):
            with SessionLocal() as db:
                Repository.usuarios.atualizar(db, usuario.id, telegram_thread_id=wa_chat_id)
            usuario.telegram_thread_id = wa_chat_id

        thread_id = getattr(usuario, "telegram_thread_id", None) or wa_chat_id
        raw_source_id = str(raw_messages[-1].id) if raw_messages else None
        tenant_id = getattr(usuario, "tenant_id", None)

        logger.info(
            "Iniciando processamento WA - user_id=%d, phone=%s, thread_id=%s, batch=%d",
            usuario.id, phone, thread_id, len(extracted),
        )

        conversa_id = None
        try:
            from backend.core.config import get_ambiente
            with SessionLocal() as db:
                conversa = get_or_create_conversa(
                    db, usuario.id, tenant_id, wa_chat_id, thread_id,
                    ambiente=get_ambiente(),
                )
                conversa_id = conversa.id
        except Exception as exc:
            logger.warning("Falha ao obter/criar conversa WA: %s", exc)

        config = {
            "configurable": {
                "thread_id": thread_id,
                "telegram_chat_id": wa_chat_id,  # agent tools use this as generic chat_id
                "telegram_message_thread_id": None,
                "source_message_id": raw_source_id,
                **_conversation_date_payload(),
                "actor_user_id": usuario.id,
                "tenant_id": tenant_id,
                "conversa_id": conversa_id,
                "actor_level": (
                    usuario.nivel_acesso.value
                    if hasattr(usuario.nivel_acesso, "value")
                    else str(usuario.nivel_acesso)
                ),
                "actor_name": usuario.nome,
                "actor_chat_display_name": display_name,
            }
        }

        runtime_location = resolve_runtime_location_context(
            tenant_id=tenant_id, obra_id_ativa=None,
        )
        config["configurable"].update(runtime_location)

        batched_text = _build_batched_text(extracted)
        result = self._invoke_agent(batched_text, config, phone, raw_messages)

        if conversa_id is not None:
            try:
                with SessionLocal() as db:
                    atualizar_ultima_mensagem(db, conversa_id, batched_text)
            except Exception as exc:
                logger.warning("Falha ao atualizar ultima_msg_em WA: %s", exc)

        return result

    def _handle_reset(self, phone: str, usuario, raw_messages: list) -> dict:
        logger.info("Reset de contexto WA - phone=%s, user_id=%d", phone, usuario.id)
        with SessionLocal() as db:
            u = Repository.usuarios.obter_por_id(db, usuario.id)
            if not u:
                persistence.mark_error(raw_messages, "usuario_nao_encontrado_reset")
                self._send_reply(phone, "Não encontrei seu usuário para reiniciar o contexto.")
                return {"ok": False, "phone": phone, "reason": "usuario_nao_encontrado_reset"}
            new_tid = _new_thread_id(phone)
            Repository.usuarios.atualizar(db, u.id, telegram_thread_id=new_tid)

        persistence.set_user(raw_messages, usuario.id)
        persistence.mark_processed(raw_messages)
        self._send_reply(
            phone,
            "Contexto da conversa reiniciado com sucesso. Vamos começar uma nova thread.\n"
            "Se quiser, me diga seu próximo registro ou dúvida.",
        )
        return {"ok": True, "phone": phone, "reason": "contexto_reiniciado", "thread_id": new_tid}

    def _invoke_agent(
        self, text: str, config: dict, phone: str, raw_messages: list
    ) -> dict:
        invoke_config = {**config, "recursion_limit": 14}
        try:
            response = graph.invoke({"messages": [HumanMessage(content=text)]}, invoke_config)
        except Exception as exc:
            try:
                from langgraph.errors import GraphRecursionError
                if isinstance(exc, GraphRecursionError):
                    logger.warning("Graph atingiu recursion_limit WA - phone=%s", phone)
                    persistence.mark_error(raw_messages, "recursion_limit")
                    self._send_reply(
                        phone,
                        "⚠️ Sua solicitação ficou complexa demais. Tente dividir em partes menores.",
                    )
                    return {"ok": False, "phone": phone, "reason": "recursion_limit"}
            except ImportError:
                pass
            logger.error("Erro ao invocar graph WA - phone=%s: %s", phone, exc, exc_info=True)
            persistence.mark_error(raw_messages, str(exc))
            self._send_reply(
                phone, "Desculpa, ocorreu um erro ao processar sua mensagem. Tente novamente."
            )
            return {"ok": False, "phone": phone, "reason": "erro_graph", "error": str(exc)}

        msgs = response.get("messages", [])
        if not msgs:
            self._send_reply(phone, "Recebi suas mensagens, mas não consegui gerar uma resposta.")
            persistence.mark_processed(raw_messages)
            return {"ok": True, "phone": phone}

        reply = (
            extract_text_content(msgs[-1].content)
            or "Recebi suas mensagens, mas não consegui gerar uma resposta em texto."
        )

        try:
            self._send_reply(phone, reply)
        except Exception as exc:
            logger.error("Erro ao enviar WA - phone=%s: %s", phone, exc, exc_info=True)
            persistence.mark_error(raw_messages, f"erro_envio: {exc}")
            return {"ok": False, "phone": phone, "reason": "erro_envio", "error": str(exc)}

        persistence.mark_processed(raw_messages)
        return {"ok": True, "phone": phone}
