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
import threading

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


def _is_image_message(message: dict) -> bool:
    return bool((message or {}).get("photo"))


def _image_batch_wait_seconds() -> float:
    raw = (os.environ.get("TELEGRAM_IMAGE_BATCH_WAIT_SECONDS") or "2.5").strip()
    try:
        value = float(raw)
        if value <= 0:
            return 2.5
        return value
    except Exception:
        return 2.5


class _ImageBatchDebouncer:
    def __init__(self, processor: MessageProcessor, wait_seconds: float) -> None:
        self._processor = processor
        self._wait_seconds = wait_seconds
        self._lock = threading.Lock()
        self._batches: dict[tuple[int, int | None], dict] = {}

    def enqueue(self, update: dict) -> int:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return 0

        thread_id = message.get("message_thread_id")
        key = (int(chat_id), int(thread_id) if thread_id is not None else None)

        with self._lock:
            bucket = self._batches.get(key)
            if not bucket:
                bucket = {"updates": [], "timer": None, "generation": 0}
                self._batches[key] = bucket

            bucket["updates"].append(update)
            bucket["generation"] += 1
            generation = int(bucket["generation"])

            existing_timer = bucket.get("timer")
            if existing_timer:
                existing_timer.cancel()

            timer = threading.Timer(
                self._wait_seconds,
                self._flush_if_current,
                args=(key, generation),
            )
            timer.daemon = True
            bucket["timer"] = timer
            timer.start()
            return len(bucket["updates"])

    def _flush_if_current(self, key: tuple[int, int | None], generation: int) -> None:
        with self._lock:
            bucket = self._batches.get(key)
            if not bucket:
                return
            if int(bucket.get("generation", 0)) != int(generation):
                return
            updates = list(bucket.get("updates") or [])
            self._batches.pop(key, None)

        if not updates:
            return

        try:
            self._processor.process(updates)
        except Exception as exc:
            logger.error("Erro ao processar lote de imagens do Telegram: %s", exc, exc_info=True)


_image_batcher = _ImageBatchDebouncer(_processor, wait_seconds=_image_batch_wait_seconds())


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

    if _is_image_message(message):
        pending = _image_batcher.enqueue(update)
        return {
            "ok": True,
            "buffered": True,
            "reason": "image_batch_queued",
            "pending_images": pending,
        }

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

