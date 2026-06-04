"""Session lifecycle management for Telegram conversations."""
from __future__ import annotations

import logging
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
    if tenant_id is None:
        raise ValueError("tenant_id é obrigatório para criar uma conversa.")

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
    if conversa:
        return conversa

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


