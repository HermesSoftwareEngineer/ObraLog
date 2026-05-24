"""Extract text/media content from WhatsApp Cloud API webhook payloads.

Single responsibility: parse raw Cloud API payloads and extract usable text,
downloading and transcribing media when needed.
"""

from __future__ import annotations

import logging

from backend.agents.llms import transcribe_audio_bytes
from backend.services.whatsapp_client import WhatsAppClient

logger = logging.getLogger(__name__)


def extract_messages(payload: dict) -> list[dict]:
    """
    Parse a Cloud API webhook payload into normalized message dicts.
    Each dict: {from_phone, display_name, message_id, type, timestamp, raw}
    """
    results: list[dict] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            value = change.get("value", {})
            contacts = {
                c["wa_id"]: c["profile"]["name"]
                for c in value.get("contacts", [])
                if c.get("wa_id") and c.get("profile", {}).get("name")
            }
            for msg in value.get("messages", []):
                from_phone = msg.get("from", "")
                results.append({
                    "from_phone": from_phone,
                    "display_name": contacts.get(from_phone, from_phone),
                    "message_id": msg.get("id", ""),
                    "timestamp": msg.get("timestamp", ""),
                    "type": msg.get("type", ""),
                    "raw": msg,
                })
    return results


class MessageExtractor:
    """Extracts usable text from a normalized WhatsApp message info dict."""

    def __init__(self, client: WhatsAppClient) -> None:
        self._client = client

    def extract(self, msg_info: dict) -> str | None:
        raw = msg_info.get("raw", {})
        msg_type = msg_info.get("type", "")

        if msg_type == "text":
            return raw.get("text", {}).get("body") or None

        if msg_type == "image":
            image = raw.get("image", {})
            media_id = image.get("id")
            caption = (image.get("caption") or "").strip()
            if media_id:
                try:
                    _bytes, _mime = self._client.download_media(media_id)
                    if caption:
                        return f"Recebi uma imagem para registro. Descrição: {caption}"
                    return "Recebi uma imagem para registro (sem descrição)."
                except Exception as exc:
                    logger.warning("Falha ao baixar imagem WA media_id=%s: %s", media_id, exc)
            return caption or None

        if msg_type in ("audio", "voice"):
            audio = raw.get("audio") or raw.get("voice") or {}
            media_id = audio.get("id")
            if media_id:
                try:
                    audio_bytes, mime = self._client.download_media(media_id)
                    clean_mime = mime.split(";")[0].strip() if ";" in mime else mime
                    transcription = transcribe_audio_bytes(audio_bytes, clean_mime).strip()
                    return transcription or None
                except Exception as exc:
                    logger.warning("Falha ao transcrever áudio WA: %s", exc)
            return None

        if msg_type == "document":
            doc = raw.get("document", {})
            caption = (doc.get("caption") or "").strip()
            filename = doc.get("filename", "arquivo")
            return caption or f"[Documento recebido: {filename}]"

        if msg_type == "location":
            loc = raw.get("location", {})
            name = loc.get("name", "")
            lat = loc.get("latitude")
            lng = loc.get("longitude")
            return f"Localização compartilhada: {name} ({lat}, {lng})"

        return None


# ---------------------------------------------------------------------------
# Agent response helpers (mirrors telegram_extractor)
# ---------------------------------------------------------------------------

def extract_text_content(content) -> str:
    """Extract plain text from an agent response message content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(p for p in parts if p).strip()
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    return str(content)
