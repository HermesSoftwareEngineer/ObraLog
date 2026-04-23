"""User linking.

Single responsibility: resolve a Telegram chat_id to a system user,
and handle the linking flow when the chat is not yet associated.
"""

from __future__ import annotations

import logging
import re

from backend.db.repository import Repository
from backend.db.session import SessionLocal
from backend.services.telegram_client import BotClient
from backend.services import telegram_persistence as persistence

logger = logging.getLogger(__name__)

_LINK_PATTERNS = [
    r"^/VINCULAR\s+([A-Z0-9]{6,12})$",
    r"^VINCULAR\s+([A-Z0-9]{6,12})$",
    r"^CODIGO\s+([A-Z0-9]{6,12})$",
    r"^([A-Z0-9]{8})$",
]


def extract_link_code(text: str) -> str | None:
    normalized = text.strip().upper()
    for pattern in _LINK_PATTERNS:
        m = re.match(pattern, normalized)
        if m:
            return m.group(1)
    return None


class UserLinker:
    """Resolves or creates user–chat associations."""

    def __init__(self, client: BotClient) -> None:
        self._client = client

    def get_user(self, chat_id):
        with SessionLocal() as db:
            return Repository.usuarios.obter_por_telegram_chat_id(db, str(chat_id))

    def handle_unlinked(
        self, chat_id, extracted_entries: list[str], raw_messages: list
    ) -> dict:
        """
        Drives the unlinked-user flow. Returns a result dict; caller should
        return this without further processing.
        """
        link_code = next(
            (extract_link_code(e) for e in extracted_entries if extract_link_code(e)),
            None,
        )

        if not link_code:
            persistence.mark_error(raw_messages, "usuario_nao_vinculado")
            self._client.send_message(
                chat_id,
                "Seu usuário ainda não está vinculado no sistema. "
                "Peça ao administrador um código de vínculo e envie: /vincular SEU_CODIGO",
            )
            return {"ok": False, "chat_id": chat_id, "reason": "usuario_nao_vinculado"}

        logger.info("Tentando vínculo com código: %s", link_code)
        with SessionLocal() as db:
            code_item = Repository.telegram_link_codes.obter_valido_por_codigo(db, link_code)
            if not code_item:
                persistence.mark_error(raw_messages, "codigo_invalido")
                self._client.send_message(
                    chat_id, "Código inválido ou expirado. Peça um novo código ao administrador."
                )
                return {"ok": False, "chat_id": chat_id, "reason": "codigo_invalido"}

            target = Repository.usuarios.obter_por_id(db, code_item.user_id)
            if not target:
                persistence.mark_error(raw_messages, "usuario_codigo_inexistente")
                self._client.send_message(
                    chat_id, "Usuário do código não encontrado. Solicite um novo código."
                )
                return {"ok": False, "chat_id": chat_id, "reason": "usuario_codigo_inexistente"}

            existing = Repository.usuarios.obter_por_telegram_chat_id(db, str(chat_id))
            if existing and existing.id != target.id:
                persistence.mark_error(raw_messages, "chat_ja_vinculado")
                self._client.send_message(chat_id, "Este Telegram já está vinculado a outro usuário.")
                return {"ok": False, "chat_id": chat_id, "reason": "chat_ja_vinculado"}

            Repository.usuarios.atualizar(
                db, target.id,
                telegram_chat_id=str(chat_id),
                telegram_thread_id=str(chat_id),
            )
            Repository.telegram_link_codes.marcar_usado(db, code_item.id)
            persistence.set_user(raw_messages, target.id)
            persistence.mark_processed(raw_messages)
            logger.info("Vínculo concluído - user_id=%d, chat_id=%s", target.id, chat_id)

        self._client.send_message(
            chat_id, "Vínculo concluído com sucesso. Agora você já pode usar o assistente."
        )
        return {"ok": True, "chat_id": chat_id, "reason": "vinculado_por_codigo"}
