"""Telegram Bot HTTP client.

Single responsibility: manage one Bot instance on one dedicated background
event loop. All Telegram HTTP I/O happens on that loop.

- Async methods: use from coroutines already running on the background loop.
- Sync methods: use from any other thread (Flask, timer callbacks, etc.).
  They submit work via run_coroutine_threadsafe and block until done.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading

from telegram import Bot
from telegram.constants import ParseMode
from telegram.request import HTTPXRequest

try:
    import telegramify_markdown
except ImportError:  # pragma: no cover - optional dependency in some environments
    telegramify_markdown = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _normalize_markdown_bullets(text: str) -> str:
    """Replace leading markdown list markers with a neutral bullet.

    Telegram markdown parser can treat leading '*' as formatting delimiters,
    which frequently breaks when the model outputs list items like
    '*   *Titulo:* ...'.
    """

    lines = text.splitlines()
    normalized: list[str] = []
    for line in lines:
        normalized.append(re.sub(r"^\s*[*-]\s+", "• ", line, count=1))
    return "\n".join(normalized)


def _escape_unbalanced_delimiter(text: str, delimiter: str) -> str:
    """Escapes delimiter if it appears unbalanced in the final text."""

    pattern = rf"(?<!\\){re.escape(delimiter)}"
    matches = list(re.finditer(pattern, text))
    if len(matches) % 2 == 0:
        return text
    return re.sub(pattern, rf"\\{delimiter}", text)


def _sanitize_markdown_for_telegram(text: str) -> str:
    sanitized = _normalize_markdown_bullets(text)
    sanitized = _escape_unbalanced_delimiter(sanitized, "*")
    sanitized = _escape_unbalanced_delimiter(sanitized, "_")
    sanitized = _escape_unbalanced_delimiter(sanitized, "`")
    return sanitized


def _convert_markdown_with_library(text: str) -> str | None:
    if telegramify_markdown is None:
        return None
    try:
        converted = telegramify_markdown.markdownify(text)
    except Exception:
        return None
    if not isinstance(converted, str):
        return None
    converted = converted.strip()
    return converted or None


def _build_markdown_candidates(text: str) -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []

    converted = _convert_markdown_with_library(text)
    if converted:
        candidates.append((converted, ParseMode.MARKDOWN_V2, "library_markdown_v2"))

    candidates.append((text, ParseMode.MARKDOWN, "raw_markdown"))

    sanitized = _sanitize_markdown_for_telegram(text)
    if sanitized != text:
        candidates.append((sanitized, ParseMode.MARKDOWN, "sanitized_markdown"))

    return candidates


class BotClient:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bot: Bot | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Loop / bot lifecycle
    # ------------------------------------------------------------------

    def get_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                loop = asyncio.new_event_loop()
                threading.Thread(
                    target=loop.run_forever, daemon=True, name="telegram-loop"
                ).start()
                token = os.environ.get("TELEGRAM_TOKEN")
                if not token:
                    raise RuntimeError("TELEGRAM_TOKEN não configurado.")
                self._bot = Bot(
                    token=token,
                    request=HTTPXRequest(connect_timeout=10, read_timeout=35),
                )
                self._loop = loop
        return self._loop

    @property
    def bot(self) -> Bot:
        self.get_loop()
        return self._bot  # type: ignore[return-value]

    def submit(self, coro, timeout: float = 45):
        """Submit a coroutine to the background loop from any external thread."""
        return asyncio.run_coroutine_threadsafe(coro, self.get_loop()).result(timeout=timeout)

    # ------------------------------------------------------------------
    # Async methods — call from coroutines already on the background loop
    # ------------------------------------------------------------------

    async def get_updates_async(self, offset: int | None = None) -> list:
        updates = await self.bot.get_updates(
            offset=offset,
            timeout=30,
            allowed_updates=["message", "callback_query"],
        )
        return [u.to_dict() for u in updates]

    async def send_message_async(self, chat_id, text: str) -> None:
        from telegram.error import BadRequest as TgBadRequest
        parse_errors: list[str] = []
        for candidate_text, mode, strategy in _build_markdown_candidates(text):
            try:
                await self.bot.send_message(chat_id=chat_id, text=candidate_text, parse_mode=mode)
                if strategy != "raw_markdown":
                    logger.info(
                        "Mensagem enviada com estratégia %s para chat_id=%s.",
                        strategy,
                        chat_id,
                    )
                return
            except TgBadRequest as exc:
                msg = str(exc)
                lowered = msg.lower()
                if "can't parse" in lowered or "parse entities" in lowered:
                    parse_errors.append(f"{strategy}: {msg}")
                    continue
                raise

        if parse_errors:
            logger.warning(
                "Falha ao enviar com markdown para chat_id=%s. Tentativas: %s. Reenviando sem formatação.",
                chat_id,
                " | ".join(parse_errors),
            )
        await self.bot.send_message(chat_id=chat_id, text=text)

    async def send_typing_async(
        self, chat_id, message_thread_id: int | None = None
    ) -> None:
        kwargs: dict = {"chat_id": chat_id, "action": "typing"}
        if message_thread_id is not None:
            kwargs["message_thread_id"] = int(message_thread_id)
        await self.bot.send_chat_action(**kwargs)

    async def download_file_async(self, file_id: str) -> tuple[bytes, str]:
        file_obj = await self.bot.get_file(file_id)
        data = await file_obj.download_as_bytearray()
        path = file_obj.file_path or ""
        if path.endswith(".mp3"):
            mime = "audio/mpeg"
        elif path.endswith(".wav"):
            mime = "audio/wav"
        elif path.endswith(".m4a"):
            mime = "audio/mp4"
        else:
            mime = "audio/ogg"
        return bytes(data), mime

    # ------------------------------------------------------------------
    # Sync wrappers — safe from Flask threads, timer callbacks, etc.
    # ------------------------------------------------------------------

    def send_message(self, chat_id, text: str) -> None:
        self.submit(self.send_message_async(chat_id, text))

    def send_typing(self, chat_id, message_thread_id: int | None = None) -> None:
        try:
            self.submit(self.send_typing_async(chat_id, message_thread_id))
        except Exception as exc:
            logger.debug("Falha ao enviar typing para chat_id=%s: %s", chat_id, exc)

    def set_webhook(self, base_url: str) -> None:
        if not base_url:
            raise RuntimeError("PUBLIC_BASE_URL não configurada.")
        url = f"{base_url.rstrip('/')}/telegram/webhook"
        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET_TOKEN")
        self.submit(self.bot.set_webhook(url=url, secret_token=secret))
        logger.info("Webhook configurado: %s", url)

    def download_file(self, file_id: str) -> tuple[bytes, str]:
        return self.submit(self.download_file_async(file_id))

    def get_image_url(self, file_id: str) -> str:
        file_obj = self.submit(self.bot.get_file(file_id))
        token = os.environ.get("TELEGRAM_TOKEN", "")
        return f"https://api.telegram.org/file/bot{token}/{file_obj.file_path}"


# Singleton used by all service modules.
bot_client = BotClient()
