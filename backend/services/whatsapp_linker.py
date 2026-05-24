"""User linking for WhatsApp.

Single responsibility: resolve a WhatsApp phone number to a system Usuario,
and handle the linking flow when the phone is not yet associated.

Linking strategy:
- Phone is stored as "wa:{e164_without_plus}" in the telegram_chat_id column
  (globally unique, no tenant scope — same guarantee as Telegram).
- obter_por_telegram_chat_id is reused since it queries globally.
"""

from __future__ import annotations

import logging
import re

from backend.db.repository import Repository
from backend.db.session import SessionLocal
from backend.services.whatsapp_client import WhatsAppClient
from backend.services import whatsapp_persistence as persistence

logger = logging.getLogger(__name__)

_LINK_PATTERNS = [
    r"^/VINCULAR\s+([A-Z0-9]{6,12})$",
    r"^VINCULAR\s+([A-Z0-9]{6,12})$",
    r"^CODIGO\s+([A-Z0-9]{6,12})$",
    r"^([A-Z0-9]{8})$",
]


def _normalize(phone: str) -> str:
    return phone.lstrip("+")


def _wa_id(phone: str) -> str:
    return f"wa:{_normalize(phone)}"


def extract_link_code(text: str) -> str | None:
    normalized = text.strip().upper()
    for pattern in _LINK_PATTERNS:
        m = re.match(pattern, normalized)
        if m:
            return m.group(1)
    return None


class UserLinker:
    """Resolves a WhatsApp phone number to a system Usuario."""

    def __init__(self, client: WhatsAppClient) -> None:
        self._client = client

    def get_user(self, phone: str):
        with SessionLocal() as db:
            return Repository.usuarios.obter_por_telegram_chat_id(db, _wa_id(phone))

    def handle_unlinked(
        self, phone: str, extracted_entries: list[str], raw_messages: list
    ) -> dict:
        link_code = next(
            (extract_link_code(e) for e in extracted_entries if extract_link_code(e)),
            None,
        )

        if not link_code:
            persistence.mark_error(raw_messages, "usuario_nao_vinculado")
            self._client.send_text_message(
                phone,
                "Seu usuário ainda não está vinculado no sistema. "
                "Peça ao administrador um código de vínculo e envie: VINCULAR SEU_CODIGO",
            )
            return {"ok": False, "phone": phone, "reason": "usuario_nao_vinculado"}

        logger.info("Vínculo WA com código=%s (phone=%s)", link_code, phone)
        with SessionLocal() as db:
            code_item = Repository.telegram_link_codes.obter_valido_por_codigo(db, link_code)
            if not code_item:
                persistence.mark_error(raw_messages, "codigo_invalido")
                self._client.send_text_message(
                    phone, "Código inválido ou expirado. Peça um novo ao administrador."
                )
                return {"ok": False, "phone": phone, "reason": "codigo_invalido"}

            target = Repository.usuarios.obter_por_id(db, code_item.user_id)
            if not target:
                persistence.mark_error(raw_messages, "usuario_codigo_inexistente")
                self._client.send_text_message(
                    phone, "Usuário do código não encontrado. Solicite um novo código."
                )
                return {"ok": False, "phone": phone, "reason": "usuario_codigo_inexistente"}

            wa_chat_id = _wa_id(phone)
            existing = Repository.usuarios.obter_por_telegram_chat_id(db, wa_chat_id)
            if existing and existing.id != target.id:
                persistence.mark_error(raw_messages, "phone_ja_vinculado")
                self._client.send_text_message(
                    phone, "Este número já está vinculado a outro usuário."
                )
                return {"ok": False, "phone": phone, "reason": "phone_ja_vinculado"}

            Repository.usuarios.atualizar(
                db, target.id,
                telegram_chat_id=wa_chat_id,
                telegram_thread_id=wa_chat_id,
            )
            Repository.telegram_link_codes.marcar_usado(db, code_item.id)
            persistence.set_user(raw_messages, target.id)
            persistence.mark_processed(raw_messages)
            logger.info("Vínculo WA concluído - user_id=%d, phone=%s", target.id, phone)

        self._client.send_text_message(
            phone,
            "Vínculo concluído com sucesso. Agora você pode usar o assistente pelo WhatsApp.",
        )
        return {"ok": True, "phone": phone, "reason": "vinculado_por_codigo"}
