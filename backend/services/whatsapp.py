"""WhatsApp service — public entry point.

Wires together the single-responsibility modules and exposes the function
used by the rest of the application:
  - handle_whatsapp_update  (webhook route)
"""

from __future__ import annotations

import logging
import threading

from backend.services.whatsapp_extractor import extract_messages

logger = logging.getLogger(__name__)


def _dispatch_direct(chat_id: str, msgs: list[dict]) -> None:
    try:
        from backend.services.whatsapp_client import WhatsAppClient
        from backend.services.whatsapp_processor import MessageProcessor
        MessageProcessor(WhatsAppClient()).process(msgs)
    except Exception as exc:
        logger.error("Erro no processamento direto WhatsApp chat_id=%s: %s", chat_id, exc, exc_info=True)


def handle_whatsapp_update(payload: dict) -> dict:
    """Dispatch a WhatsApp Cloud API webhook payload directly to the processor."""
    messages = extract_messages(payload)
    if not messages:
        return {"ok": True, "ignored": True, "reason": "sem_mensagens"}

    by_phone: dict[str, list[dict]] = {}
    for msg in messages:
        by_phone.setdefault(msg["from_phone"], []).append(msg)

    dispatched = []
    for phone, msgs in by_phone.items():
        chat_id = f"wa:{phone}"
        threading.Thread(
            target=_dispatch_direct,
            args=(chat_id, msgs),
            daemon=True,
            name=f"agent-whatsapp-{phone}",
        ).start()
        dispatched.append({"chat_id": chat_id, "dispatched": True})

    return {"ok": True, "dispatched": dispatched} if len(dispatched) != 1 else {"ok": True, "dispatched": True}
