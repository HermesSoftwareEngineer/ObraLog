"""Batch queue.

Single responsibility: debounce rapid messages per chat and flush them
together to the processor after a quiet window.
"""

from __future__ import annotations

import logging
import os
import threading

from backend.services.telegram_processor import MessageProcessor

logger = logging.getLogger(__name__)

_DEBOUNCE = float(os.environ.get("TELEGRAM_MESSAGE_BATCH_DEBOUNCE_SECONDS", "1.2"))


class BatchQueue:
    """Accumulates updates per chat_id and flushes after a debounce window."""

    def __init__(self, processor: MessageProcessor) -> None:
        self._processor = processor
        self._lock = threading.Lock()
        self._pending: dict[str, list[dict]] = {}
        self._timers: dict[str, threading.Timer] = {}

    def enqueue(self, update: dict) -> dict:
        message = update.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        if chat_id is None:
            return {"ok": True, "ignored": True}

        chat_key = str(chat_id)
        with self._lock:
            self._pending.setdefault(chat_key, []).append(update)
            if timer := self._timers.get(chat_key):
                timer.cancel()
            timer = threading.Timer(_DEBOUNCE, self._flush, args=(chat_key,))
            timer.daemon = True
            self._timers[chat_key] = timer
            timer.start()

        return {"ok": True, "queued": True, "chat_id": chat_id}

    def _flush(self, chat_key: str) -> None:
        with self._lock:
            updates = self._pending.pop(chat_key, [])
            self._timers.pop(chat_key, None)
        if not updates:
            return
        try:
            self._processor.process(updates)
        except Exception as exc:
            logger.error(
                "Falha ao processar batch do chat %s: %s", chat_key, exc, exc_info=True
            )
