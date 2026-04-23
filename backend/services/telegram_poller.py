"""Long-polling loop.

Single responsibility: fetch updates from the Telegram API and hand them to
the dispatch function. Runs entirely as an async coroutine on the BotClient's
background event loop — so typing actions use await directly, avoiding the
sync-wrapper deadlock that would occur if run_coroutine_threadsafe were called
from within the same loop.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable

from backend.services.telegram_client import BotClient

logger = logging.getLogger(__name__)


class Poller:
    """Drives long-polling on the BotClient background loop."""

    def __init__(self, client: BotClient, dispatch_fn: Callable) -> None:
        self._client = client
        self._dispatch = dispatch_fn
        self._started = False
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._started:
                logger.info("Polling já está ativo. Ignorando.")
                return
            self._started = True
        # Submit the coroutine to the background loop (fire-and-forget).
        asyncio.run_coroutine_threadsafe(self._loop(), self._client.get_loop())
        logger.info("Polling do Telegram iniciado.")

    async def _loop(self) -> None:
        offset = None
        errors = 0

        while True:
            try:
                updates = await self._client.get_updates_async(offset)
                errors = 0

                for update in updates:
                    try:
                        await self._send_typing(update)
                        # dispatch is sync (just enqueues); safe to call from async context.
                        self._dispatch(update, typing_already_sent=True)
                        offset = update.get("update_id", 0) + 1
                    except Exception as exc:
                        logger.error(
                            "Erro ao processar update %s: %s",
                            update.get("update_id"), exc, exc_info=True,
                        )

                if not updates:
                    await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                logger.info("Polling cancelado.")
                break

            except Exception as exc:
                errors += 1
                wait = min(2 ** errors, 60)
                logger.warning(
                    "Erro no polling (%d): %s. Aguardando %ds...", errors, exc, wait
                )
                if errors >= 5:
                    logger.error("Muitos erros consecutivos. Encerrando polling.")
                    raise
                await asyncio.sleep(wait)

    async def _send_typing(self, update: dict) -> None:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        if cid := chat.get("id"):
            try:
                # Await directly — we are already on the background loop.
                await self._client.send_typing_async(cid, message.get("message_thread_id"))
            except Exception as exc:
                logger.debug("Falha ao enviar typing: %s", exc)
