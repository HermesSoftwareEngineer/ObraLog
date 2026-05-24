"""WhatsApp service — public entry point.

Wires together the single-responsibility modules and exposes the function
used by the rest of the application:
  - handle_whatsapp_update  (webhook route)
"""

from __future__ import annotations

import logging

from backend.services.whatsapp_client import wa_client
from backend.services.whatsapp_extractor import extract_messages
from backend.services.whatsapp_processor import MessageProcessor

logger = logging.getLogger(__name__)

_processor = MessageProcessor(wa_client)


def handle_whatsapp_update(payload: dict) -> dict:
    """Dispatch a WhatsApp Cloud API webhook payload to the agent."""
    messages = extract_messages(payload)
    if not messages:
        return {"ok": True, "ignored": True, "reason": "sem_mensagens"}

    # Group by phone — in practice each webhook payload has one sender,
    # but we handle multiple gracefully.
    by_phone: dict[str, list[dict]] = {}
    for msg in messages:
        by_phone.setdefault(msg["from_phone"], []).append(msg)

    results = []
    for phone, msgs in by_phone.items():
        result = _processor.process(msgs)
        results.append(result)

    return results[0] if len(results) == 1 else {"ok": True, "results": results}
