"""Telegram service — public entry points.

Wires together the single-responsibility modules and exposes the three
functions used by the rest of the application:
  - handle_telegram_update  (webhook route)
  - start_polling            (development / standalone mode)
  - set_webhook              (startup configuration)
"""

from __future__ import annotations

import logging
import os

from backend.services.telegram_client import bot_client
from backend.services.telegram_processor import MessageProcessor
from backend.services.telegram_poll import PollAnswerHandler
from backend.services.telegram_poller import Poller

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Component wiring
# ---------------------------------------------------------------------------

_processor = MessageProcessor(bot_client)
_poll_handler = PollAnswerHandler(bot_client)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def handle_telegram_update(update: dict, *, typing_already_sent: bool = False) -> dict:
    if poll_answer := update.get("poll_answer"):
        return _poll_handler.handle(poll_answer)
    if update.get("edited_message") and not update.get("message"):
        return {"ok": True, "ignored": True, "reason": "edited_message_ignored"}

    message = update.get("message") or {}
    chat = message.get("chat") or {}
    if chat.get("id") is None:
        return {"ok": True, "ignored": True, "reason": "update_sem_chat_id"}

    if not typing_already_sent:
        if cid := chat.get("id"):
            bot_client.send_typing(cid, message.get("message_thread_id"))
    return _processor.process([update])


def set_webhook(base_url: str) -> None:
    bot_client.set_webhook(base_url)


def start_polling() -> None:
    if os.environ.get("TELEGRAM_POLLING_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}:
        for name in ("httpcore", "httpx", "telegram", "telegram.request", "telegram.ext"):
            logging.getLogger(name).setLevel(logging.DEBUG)
    _poller.start()


_poller = Poller(bot_client, dispatch_fn=handle_telegram_update)

