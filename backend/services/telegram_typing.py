"""Typing indicator.

Single responsibility: send periodic 'typing' actions while the agent
is processing, keeping the user informed.
"""

from __future__ import annotations

import logging
import os
import threading

from backend.services.telegram_client import BotClient

logger = logging.getLogger(__name__)


def _env_bool(key: str, default: str = "false") -> bool:
    return os.environ.get(key, default).strip().lower() in {"1", "true", "yes", "on"}


def _typing_interval() -> float:
    try:
        return max(1.0, float(os.environ.get("TELEGRAM_TYPING_INTERVAL_SECONDS", "3.5")))
    except (TypeError, ValueError):
        return 3.5


class TypingIndicator:
    """Starts a daemon thread that repeatedly sends 'typing' until stopped."""

    def __init__(self, client: BotClient) -> None:
        self._client = client

    def start(self, chat_id, message_thread_id: int | None = None):
        """Start sending typing. Returns a callable that stops it."""
        if not _env_bool("TELEGRAM_TYPING_INDICATOR_ENABLED", "true"):
            return lambda: None

        stop = threading.Event()
        interval = _typing_interval()

        def _loop() -> None:
            while not stop.is_set():
                self._client.send_typing(chat_id, message_thread_id)
                stop.wait(interval)

        t = threading.Thread(target=_loop, daemon=True, name=f"typing-{chat_id}")
        t.start()

        def _stop() -> None:
            stop.set()
            t.join(timeout=0.3)

        return _stop
