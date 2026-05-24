"""WhatsApp Cloud API HTTP client.

Single responsibility: all HTTP I/O against the Meta Graph API.
Uses synchronous httpx (no background loop needed — the WA API is REST,
not long-polling, so there is no event loop to manage).
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_GRAPH_VERSION = "v19.0"
_BASE = f"https://graph.facebook.com/{_GRAPH_VERSION}"


def _token() -> str:
    t = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
    if not t:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN não configurado.")
    return t


def _phone_id() -> str:
    p = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
    if not p:
        raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID não configurado.")
    return p


class WhatsAppClient:
    """Thin HTTP wrapper around the WhatsApp Cloud API."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send_text_message(self, to_phone: str, text: str) -> dict | None:
        """Send a text message. Returns {message_id, to} or None on failure."""
        url = f"{_BASE}/{_phone_id()}/messages"
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone.lstrip("+"),
            "type": "text",
            "text": {"body": text, "preview_url": False},
        }
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(url, json=body, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                msgs = data.get("messages", [])
                if msgs:
                    return {"message_id": msgs[0]["id"], "to": to_phone}
                return data
        except Exception as exc:
            logger.error("Erro ao enviar WA para %s: %s", to_phone, exc)
            return None

    def mark_as_read(self, message_id: str) -> None:
        """Mark a received message as read (WA receipt indicator)."""
        url = f"{_BASE}/{_phone_id()}/messages"
        body = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        try:
            with httpx.Client(timeout=10) as client:
                client.post(url, json=body, headers=self._headers())
        except Exception as exc:
            logger.debug("Falha ao marcar WA como lido (%s): %s", message_id, exc)

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------

    def download_media(self, media_id: str) -> tuple[bytes, str]:
        """Download media by ID. Returns (bytes, mime_type)."""
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{_BASE}/{media_id}", headers=self._headers())
            resp.raise_for_status()
            meta = resp.json()

        url = meta.get("url", "")
        mime = meta.get("mime_type", "application/octet-stream")

        with httpx.Client(timeout=60) as client:
            resp = client.get(url, headers=self._headers())
            resp.raise_for_status()

        return resp.content, mime


wa_client = WhatsAppClient()
