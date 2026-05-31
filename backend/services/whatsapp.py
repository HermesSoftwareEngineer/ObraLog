"""WhatsApp service — public entry point.

Wires together the single-responsibility modules and exposes the function
used by the rest of the application:
  - handle_whatsapp_update  (webhook route)
"""

from __future__ import annotations

import logging

from backend.services.whatsapp_extractor import extract_messages
from backend.workers.agent_worker import enqueue as _enqueue_job

logger = logging.getLogger(__name__)


def handle_whatsapp_update(payload: dict) -> dict:
    """Dispatch a WhatsApp Cloud API webhook payload to the agent job queue."""
    messages = extract_messages(payload)
    if not messages:
        return {"ok": True, "ignored": True, "reason": "sem_mensagens"}

    by_phone: dict[str, list[dict]] = {}
    for msg in messages:
        by_phone.setdefault(msg["from_phone"], []).append(msg)

    queued = []
    for phone, msgs in by_phone.items():
        chat_id = f"wa:{phone}"
        try:
            _enqueue_job("whatsapp", chat_id, msgs)
            queued.append({"chat_id": chat_id, "queued": True})
        except Exception as exc:
            logger.error("Falha ao enfileirar job WA phone=%s: %s", phone, exc, exc_info=True)
            queued.append({"chat_id": chat_id, "queued": False, "error": str(exc)})

    return {"ok": True, "queued": queued} if len(queued) != 1 else {"ok": True, "queued": True}
