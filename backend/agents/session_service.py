"""Session lifecycle management for Telegram conversations."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db.models import Conversa

logger = logging.getLogger("obralog.session_service")


def get_or_create_conversa(
    db: Session,
    usuario_id: int,
    tenant_id: int | None,
    chat_id: str,
    thread_id: str,
    ambiente: str = "prod",
) -> Conversa:
    """Return the open Conversa for this user or create a new one."""
    _t0 = time.monotonic()
    logger.info("[SESSION_SVC] get_or_create_conversa: início usuario_id=%s tenant_id=%s chat_id=%s", usuario_id, tenant_id, chat_id)

    if tenant_id is None:
        raise ValueError("tenant_id é obrigatório para criar uma conversa.")

    _t = time.monotonic()
    conversa = (
        db.query(Conversa)
        .filter(
            Conversa.usuario_id == usuario_id,
            Conversa.tenant_id == tenant_id,
            Conversa.encerrada_em.is_(None),
        )
        .order_by(Conversa.iniciada_em.desc())
        .first()
    )
    logger.info("[SESSION_SVC] get_or_create_conversa: query=%.3fs conversa_existente=%s", time.monotonic() - _t, conversa is not None)

    if conversa:
        logger.info("[SESSION_SVC] get_or_create_conversa: retornando existente id=%s total=%.3fs", conversa.id, time.monotonic() - _t0)
        return conversa

    _t = time.monotonic()
    result = db.execute(
        text(
            "INSERT INTO conversas (tenant_id, usuario_id, chat_id, thread_id, ambiente)"
            " VALUES (:tenant_id, :usuario_id, :chat_id, :thread_id, :ambiente)"
            " RETURNING id"
        ),
        {
            "tenant_id": tenant_id,
            "usuario_id": usuario_id,
            "chat_id": chat_id,
            "thread_id": thread_id,
            "ambiente": ambiente,
        },
    )
    db.commit()
    new_id = result.scalar()
    logger.info("[SESSION_SVC] get_or_create_conversa: INSERT+commit=%.3fs novo_id=%s total=%.3fs", time.monotonic() - _t, new_id, time.monotonic() - _t0)
    return db.query(Conversa).filter(Conversa.id == new_id).first()


def atualizar_ultima_mensagem(
    db: Session,
    conversa_id: int,
    texto: Optional[str] = None,
) -> None:
    """Stamp ultima_msg_em and update resumo if not yet set."""
    conversa = db.query(Conversa).filter(Conversa.id == conversa_id).first()
    if not conversa:
        return

    conversa.ultima_msg_em = datetime.now(timezone.utc)

    if texto and not conversa.resumo:
        conversa.resumo = texto[:500]

    db.commit()


def encerrar_conversa(db: Session, conversa_id: int) -> None:
    """Mark a conversation as closed."""
    conversa = db.query(Conversa).filter(Conversa.id == conversa_id).first()
    if not conversa or conversa.encerrada_em is not None:
        return
    conversa.encerrada_em = datetime.now(timezone.utc)
    db.commit()


