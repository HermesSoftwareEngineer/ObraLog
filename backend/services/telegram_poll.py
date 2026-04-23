"""Poll answer handler.

Single responsibility: receive poll_answer updates, look up poll context,
and route the response through the agent.
"""

from __future__ import annotations

import logging
from datetime import datetime

from langchain_core.messages import HumanMessage

try:
    from backend.agents.graph import graph
except ImportError:
    from agents.graph import graph  # type: ignore[no-redef]

from backend.db.repository import Repository
from backend.db.session import SessionLocal
from backend.services.telegram_client import BotClient
from backend.services.telegram_extractor import extract_text_content, response_used_telegram_ui
from backend.services.telegram_interactions import get_poll_context

logger = logging.getLogger(__name__)


def _conversation_date_payload() -> dict:
    now = datetime.now()
    return {
        "conversation_date": now.date().isoformat(),
        "conversation_date_br": now.strftime("%d/%m/%Y"),
    }


class PollAnswerHandler:
    """Routes poll_answer updates through the agent."""

    def __init__(self, client: BotClient) -> None:
        self._client = client

    def handle(self, poll_answer: dict) -> dict:
        poll_id = poll_answer.get("poll_id")
        if not poll_id:
            return {"ok": True, "ignored": True, "reason": "poll_answer_sem_poll_id"}

        context = get_poll_context(str(poll_id))
        if not context:
            return {"ok": True, "ignored": True, "reason": "poll_context_nao_encontrado"}

        chat_id = context.get("chat_id")
        thread_id = context.get("thread_id")
        thread_msg_id = context.get("telegram_message_thread_id")
        actor_user_id = context.get("actor_user_id")
        actor_level = context.get("actor_level")
        question = context.get("question") or "Checklist"
        options = context.get("options") or []
        option_ids = poll_answer.get("option_ids") or []

        if not chat_id or thread_id is None or actor_user_id is None or actor_level is None:
            return {"ok": True, "ignored": True, "reason": "poll_context_incompleto"}

        selected = [
            options[i] for i in option_ids if isinstance(i, int) and 0 <= i < len(options)
        ]
        if selected:
            text = (
                f"Resposta de enquete recebida. Pergunta: {question}. "
                f"Opções selecionadas: {', '.join(selected)}."
            )
        else:
            text = f"Resposta de enquete recebida. Pergunta: {question}. Nenhuma opção selecionada."

        with SessionLocal() as db:
            usuario = Repository.usuarios.obter_por_id(db, int(actor_user_id))

        if not usuario:
            self._client.send_message(
                chat_id,
                "Recebi a resposta da enquete, mas não localizei o usuário vinculado.",
            )
            return {"ok": False, "chat_id": chat_id, "reason": "usuario_enquete_nao_encontrado"}

        chat_user = poll_answer.get("user") or {}
        display_name = (
            chat_user.get("first_name")
            or chat_user.get("username")
            or usuario.nome
            or str(chat_id)
        )

        config = {
            "configurable": {
                "thread_id": str(thread_id),
                "telegram_chat_id": str(chat_id),
                "telegram_message_thread_id": int(thread_msg_id) if thread_msg_id is not None else None,
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

        response = graph.invoke({"messages": [HumanMessage(content=text)]}, config)
        msgs = response["messages"]
        reply = extract_text_content(msgs[-1].content) if msgs else ""
        if not reply:
            reply = "Resposta da enquete recebida."
        if not response_used_telegram_ui(msgs):
            self._client.send_message(chat_id, reply)

        return {"ok": True, "chat_id": chat_id, "reason": "poll_answer_processado"}
