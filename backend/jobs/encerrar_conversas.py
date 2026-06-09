"""Standalone job: close conversations that exceeded tenant timeout.

Usage:
    python -m backend.jobs.encerrar_conversas
"""
from __future__ import annotations

import logging
import sys

from sqlalchemy import text

logger = logging.getLogger("obralog.jobs.encerrar_conversas")


def _get_messages_from_checkpoint(thread_id: str) -> list:
    """Recupera mensagens do checkpointer LangGraph para a thread dada."""
    try:
        from backend.agents.chat_db import checkpointer
        from backend.services.telegram_processor import _scoped_thread_id
        cfg = {"configurable": {"thread_id": _scoped_thread_id(thread_id)}}
        checkpoint = checkpointer.get(cfg)
        if checkpoint:
            return checkpoint.get("channel_values", {}).get("messages", []) or []
    except Exception as exc:
        logger.debug("Falha ao recuperar checkpoint thread_id=%s: %s", thread_id, exc)
    return []


def run() -> None:
    from backend.db.session import SessionLocal
    from backend.agents.session_service import encerrar_conversa
    from backend.agents.compactacao import compactar_conversa
    from backend.db.models import Conversa

    with SessionLocal() as db:
        result = db.execute(
            text(
                """
                SELECT c.id, c.thread_id
                FROM conversas c
                JOIN tenants t ON t.id = c.tenant_id
                WHERE c.encerrada_em IS NULL
                  AND c.ultima_msg_em < now() - (t.timeout_conversa_minutos || ' minutes')::interval
                """
            )
        )
        rows = [(row[0], row[1]) for row in result]

    if not rows:
        logger.info("Nenhuma conversa para encerrar.")
        return

    logger.info("Encerrando %d conversa(s) por timeout.", len(rows))
    for conversa_id, thread_id in rows:
        try:
            messages = _get_messages_from_checkpoint(thread_id) if thread_id else []
            with SessionLocal() as db:
                compactar_conversa(db, conversa_id, messages, compress_state=False)
                encerrar_conversa(db, conversa_id)
        except Exception as exc:
            logger.error("Falha ao encerrar conversa %d: %s", conversa_id, exc)

    logger.info("Job concluído.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    run()
