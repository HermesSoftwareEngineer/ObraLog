"""Session lifecycle management for Telegram conversations."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db.models import Conversa
from backend.utils.embeddings import gerar_embedding

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

    # Use raw INSERT to avoid psycopg3 casting embedding=None as ::VARCHAR
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
    embedding: Optional[list[float]] = None,
) -> None:
    """Stamp ultima_msg_em and optionally update the embedding/resumo.

    Accepts a pre-computed embedding to avoid duplicate gerar_embedding() calls.
    """
    conversa = db.query(Conversa).filter(Conversa.id == conversa_id).first()
    if not conversa:
        return

    conversa.ultima_msg_em = datetime.now(timezone.utc)

    if texto:
        if not conversa.resumo:
            conversa.resumo = texto[:500]

        # Use provided embedding or generate one if not supplied
        emb = embedding if embedding is not None else gerar_embedding(texto)
        if emb is not None:
            # ORM não sabe fazer cast list → vector no psycopg3, gerando ::VARCHAR.
            # Flush os campos simples primeiro, depois atualiza embedding via raw SQL.
            db.flush()
            emb_literal = "[" + ",".join(str(v) for v in emb) + "]"
            db.execute(
                text("UPDATE conversas SET embedding = CAST(:emb AS vector) WHERE id = :id"),
                {"emb": emb_literal, "id": conversa_id},
            )

    db.commit()


def encerrar_conversa(db: Session, conversa_id: int) -> None:
    """Mark a conversation as closed."""
    conversa = db.query(Conversa).filter(Conversa.id == conversa_id).first()
    if not conversa or conversa.encerrada_em is not None:
        return
    conversa.encerrada_em = datetime.now(timezone.utc)
    db.commit()


def buscar_memorias_relevantes(
    db: Session,
    tenant_id: int,
    texto: str,
    top_k: int = 3,
) -> list[str]:
    """Return summaries of closed conversations most similar to `texto`."""
    embedding = gerar_embedding(texto)
    if embedding is None:
        return []
    return buscar_memorias_com_embedding(db, tenant_id, embedding, top_k)


def buscar_memorias_com_embedding(
    db: Session,
    tenant_id: int,
    embedding: list[float],
    top_k: int = 3,
) -> list[str]:
    """Same as buscar_memorias_relevantes but accepts a pre-computed embedding.

    Use this when the embedding was already generated to avoid a duplicate API call.
    """
    # pgvector <=> is cosine distance (smaller = more similar)
    emb_literal = "[" + ",".join(str(v) for v in embedding) + "]"
    try:
        result = db.execute(
            text(
                """
                SELECT resumo
                FROM conversas
                WHERE tenant_id  = :tenant_id
                  AND encerrada_em IS NOT NULL
                  AND resumo      IS NOT NULL
                  AND embedding   IS NOT NULL
                ORDER BY embedding <=> CAST(:emb AS vector)
                LIMIT :top_k
                """
            ),
            {"tenant_id": tenant_id, "emb": emb_literal, "top_k": top_k},
        )
        return [row[0] for row in result if row[0]]
    except Exception as exc:
        logger.warning("buscar_memorias_com_embedding falhou: %s", exc)
        return []
