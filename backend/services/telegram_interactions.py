from __future__ import annotations

import time
from threading import Lock


_POLL_CACHE_LOCK = Lock()
_POLL_CACHE: dict[str, dict] = {}
_POLL_CACHE_TTL_SECONDS = 60 * 60 * 24


def _cleanup_expired_locked() -> None:
    now = time.time()
    expired_keys = [
        poll_id
        for poll_id, payload in _POLL_CACHE.items()
        if now - float(payload.get("created_at", now)) > _POLL_CACHE_TTL_SECONDS
    ]
    for poll_id in expired_keys:
        _POLL_CACHE.pop(poll_id, None)


def register_poll_context(
    poll_id: str,
    *,
    chat_id: str,
    thread_id: str,
    telegram_message_thread_id: int | None,
    actor_user_id: int,
    actor_level: str,
    question: str,
    options: list[str],
) -> None:
    with _POLL_CACHE_LOCK:
        _cleanup_expired_locked()
        _POLL_CACHE[poll_id] = {
            "chat_id": str(chat_id),
            "thread_id": str(thread_id),
            "telegram_message_thread_id": telegram_message_thread_id,
            "actor_user_id": int(actor_user_id),
            "actor_level": str(actor_level),
            "question": question,
            "options": list(options),
            "created_at": time.time(),
        }


def get_poll_context(poll_id: str) -> dict | None:
    with _POLL_CACHE_LOCK:
        payload = _POLL_CACHE.get(poll_id)
        if not payload:
            return None
        now = time.time()
        if now - float(payload.get("created_at", now)) > _POLL_CACHE_TTL_SECONDS:
            _POLL_CACHE.pop(poll_id, None)
            return None
        return dict(payload)