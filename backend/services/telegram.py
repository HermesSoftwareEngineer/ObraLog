"""Telegram service — public entry points.

Wires together the single-responsibility modules and exposes the three
functions used by the rest of the application:
  - handle_telegram_update  (webhook route)
  - start_polling            (development / standalone mode)
  - set_webhook              (startup configuration)
"""

from __future__ import annotations
print("[BOOT] telegram.py: módulo carregando...", flush=True)

import logging
import os
import threading

_OBRALOG_ENV = os.environ.get("OBRALOG_ENV", "prod")

print("[BOOT] telegram.py: importando telegram_client...", flush=True)
from backend.services.telegram_client import bot_client
print("[BOOT] telegram.py: telegram_client OK", flush=True)

print("[BOOT] telegram.py: importando telegram_poll...", flush=True)
from backend.services.telegram_poll import PollAnswerHandler
print("[BOOT] telegram.py: telegram_poll OK", flush=True)

print("[BOOT] telegram.py: importando telegram_poller...", flush=True)
from backend.services.telegram_poller import Poller
print("[BOOT] telegram.py: telegram_poller OK", flush=True)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Component wiring
# ---------------------------------------------------------------------------

print("[BOOT] telegram.py: criando _poll_handler...", flush=True)
_poll_handler = PollAnswerHandler(bot_client)
print("[BOOT] telegram.py: _poll_handler criado OK", flush=True)


def _dispatch_direct(updates: list[dict]) -> None:
    """Processa updates diretamente em thread de background, sem passar pela fila de jobs."""
    try:
        from backend.services.telegram_processor import MessageProcessor
        MessageProcessor(bot_client).process(updates)
    except Exception as exc:
        logger.error("Erro no processamento direto Telegram: %s", exc, exc_info=True)


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


_IMAGE_BATCH_MAX = 10


class _ImageBatchDebouncer:
    def __init__(self, wait_seconds: float) -> None:
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

        flush_now = False
        with self._lock:
            bucket = self._batches.get(key)
            if not bucket:
                bucket = {"updates": [], "timer": None, "generation": 0}
                self._batches[key] = bucket

            bucket["updates"].append(update)
            pending = len(bucket["updates"])

            if pending >= _IMAGE_BATCH_MAX:
                # Limite atingido — cancela o timer e flush imediato
                existing_timer = bucket.get("timer")
                if existing_timer:
                    existing_timer.cancel()
                self._batches.pop(key, None)
                flush_now = True
                updates_to_flush = list(bucket["updates"])
            else:
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

        if flush_now:
            self._dispatch(str(key[0]), updates_to_flush)
            return len(updates_to_flush)

        with self._lock:
            return len(self._batches.get(key, {}).get("updates", []))

    def _dispatch(self, chat_id: str, updates: list[dict]) -> None:
        if not updates:
            return
        try:
            from backend.jobs.agent_worker import enqueue_job
            enqueue_job(canal="telegram", chat_id=chat_id, payload={"updates": updates}, env=_OBRALOG_ENV)
        except Exception as exc:
            logger.error("Erro ao enfileirar lote de imagens do Telegram: %s", exc, exc_info=True)

    def _flush_if_current(self, key: tuple[int, int | None], generation: int) -> None:
        with self._lock:
            bucket = self._batches.get(key)
            if not bucket:
                return
            if int(bucket.get("generation", 0)) != int(generation):
                return
            updates = list(bucket.get("updates") or [])
            self._batches.pop(key, None)

        self._dispatch(str(key[0]), updates)


_image_batcher = _ImageBatchDebouncer(wait_seconds=_image_batch_wait_seconds())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def handle_telegram_update(update: dict, typing_already_sent: bool = False) -> dict:
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

    from backend.jobs.agent_worker import enqueue_job
    chat_id = str(chat.get("id", ""))
    enqueue_job(canal="telegram", chat_id=chat_id, payload={"updates": [update]}, env=_OBRALOG_ENV)
    return {"ok": True, "dispatched": True}


def set_webhook(base_url: str) -> None:
    bot_client.set_webhook(base_url)


def start_polling() -> None:
    if os.environ.get("TELEGRAM_POLLING_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}:
        for name in ("httpcore", "httpx", "telegram", "telegram.request", "telegram.ext"):
            logging.getLogger(name).setLevel(logging.DEBUG)
    try:
        bot_client.delete_webhook()
    except Exception as exc:
        logging.getLogger(__name__).warning("Falha ao remover webhook antes do polling: %s", exc)
    _poller.start()


_poller = Poller(bot_client, dispatch_fn=handle_telegram_update)

