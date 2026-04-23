"""Raw message persistence.

Single responsibility: save incoming Telegram messages to mensagens_campo
and update their processing status.
"""

from __future__ import annotations

import hashlib
import json

from backend.db.models import ConteudoMensagemTipo
from backend.db.repository import Repository
from backend.db.session import SessionLocal


def _detect_content_type(message: dict) -> ConteudoMensagemTipo:
    has_text = bool(message.get("text") or message.get("caption"))
    has_photo = bool(message.get("photo"))
    has_audio = bool(message.get("voice") or message.get("audio"))
    if (has_photo or has_audio) and has_text:
        return ConteudoMensagemTipo.MISTO
    if has_photo:
        return ConteudoMensagemTipo.FOTO
    if has_audio:
        return ConteudoMensagemTipo.AUDIO
    return ConteudoMensagemTipo.TEXTO


def _message_hash(chat_id, message_id, update_id) -> str:
    base = (
        f"telegram:{chat_id}:{message_id}"
        if message_id is not None
        else f"telegram:{chat_id}:-:{update_id or '-'}"
    )
    return hashlib.sha256(base.encode()).hexdigest()


def persist(
    *,
    update: dict,
    message: dict,
    chat_id,
    texto_extraido: str | None,
    usuario_id: int | None,
):
    message_id = message.get("message_id")
    update_id = update.get("update_id")
    with SessionLocal() as db:
        return Repository.mensagens_campo.criar_telegram(
            db,
            telegram_chat_id=str(chat_id),
            telegram_message_id=message_id,
            telegram_update_id=update_id,
            texto_bruto=texto_extraido,
            texto_normalizado=" ".join(str(texto_extraido or "").strip().split()) or None,
            payload_json=json.dumps(update, ensure_ascii=False),
            hash_idempotencia=_message_hash(chat_id, message_id, update_id),
            tipo_conteudo=_detect_content_type(message),
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
