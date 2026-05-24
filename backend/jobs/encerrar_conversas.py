"""Standalone job: close conversations that exceeded tenant timeout.

Usage:
    python -m backend.jobs.encerrar_conversas
"""
from __future__ import annotations

import logging
import sys

from sqlalchemy import text

logger = logging.getLogger("obralog.jobs.encerrar_conversas")


def run() -> None:
    from backend.db.session import SessionLocal
    from backend.agents.session_service import encerrar_conversa

    with SessionLocal() as db:
        result = db.execute(
            text(
                """
                SELECT c.id
                FROM conversas c
                JOIN tenants t ON t.id = c.tenant_id
                WHERE c.encerrada_em IS NULL
                  AND c.ultima_msg_em < now() - (t.timeout_conversa_minutos || ' minutes')::interval
                """
            )
        )
        ids = [row[0] for row in result]

    if not ids:
        logger.info("Nenhuma conversa para encerrar.")
        return

    logger.info("Encerrando %d conversa(s) por timeout.", len(ids))
    for conversa_id in ids:
        try:
            with SessionLocal() as db:
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
