"""Raw message persistence for WhatsApp.

Single responsibility: save incoming WhatsApp messages to mensagens_campo
and update their processing status. Mirrors telegram_persistence.py.
"""

from __future__ import annotations

import hashlib
import json

from backend.db.models import ConteudoMensagemTipo
from backend.db.repository import Repository
from backend.db.session import SessionLocal


def _detect_content_type(msg_type: str) -> ConteudoMensagemTipo:
    if msg_type in ("audio", "voice"):
        return ConteudoMensagemTipo.AUDIO
    if msg_type == "image":
        return ConteudoMensagemTipo.FOTO
    return ConteudoMensagemTipo.TEXTO


def _message_hash(phone: str, message_id: str) -> str:
    base = f"whatsapp:{phone}:{message_id}"
    return hashlib.sha256(base.encode()).hexdigest()


def persist(
    *,
    msg_info: dict,
    texto_extraido: str | None,
    usuario_id: int | None,
):
    phone = msg_info["from_phone"]
    message_id = msg_info["message_id"]
    with SessionLocal() as db:
        return Repository.mensagens_campo.criar_whatsapp(
            db,
            chat_id=f"wa:{phone}",
            message_id=message_id,
            texto_bruto=texto_extraido,
            texto_normalizado=" ".join(str(texto_extraido or "").strip().split()) or None,
            payload_json=json.dumps(msg_info.get("raw", {}), ensure_ascii=False),
            hash_idempotencia=_message_hash(phone, message_id),
            tipo_conteudo=_detect_content_type(msg_info.get("type", "text")),
            usuario_id=usuario_id,
        )


def mark_processed(raw_messages: list) -> None:
    if not raw_messages:
        return
    with SessionLocal() as db:
        for rm in raw_messages:
            Repository.mensagens_campo.marcar_processada(db, rm.id)


def mark_error(raw_messages: list, reason: str) -> None:
    if not raw_messages:
        return
    with SessionLocal() as db:
        for rm in raw_messages:
            Repository.mensagens_campo.marcar_erro(db, rm.id, reason)


def set_user(raw_messages: list, usuario_id: int) -> None:
    if not raw_messages:
        return
    with SessionLocal() as db:
        for rm in raw_messages:
            Repository.mensagens_campo.atualizar_usuario(db, rm.id, usuario_id)
