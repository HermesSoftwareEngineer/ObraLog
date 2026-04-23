"""Message content extraction.

Single responsibility: extract a plain-text representation from a raw
Telegram message dict (text, photo caption, or transcribed audio).
Also provides helpers to parse agent response content.
"""

from __future__ import annotations

import logging

from backend.agents.llms import transcribe_audio_bytes
from backend.services.telegram_client import BotClient

logger = logging.getLogger(__name__)


class MessageExtractor:
    """Extracts usable text from a Telegram message dict."""

    def __init__(self, client: BotClient) -> None:
        self._client = client

    def extract(self, message: dict, chat_id) -> str | None:
        if text := message.get("text"):
            return text

        if photos := (message.get("photo") or []):
            file_id = photos[-1].get("file_id")
            if not file_id:
                raise RuntimeError("Imagem recebida sem file_id.")
            try:
                url = self._client.get_image_url(file_id)
            except Exception as exc:
                logger.warning("Não foi possível obter URL da imagem: %s", exc)
                url = f"telegram://{file_id}"
            caption = (message.get("caption") or "").strip()
            if caption:
                return (
                    f"Recebi uma imagem para registro. URL da imagem: {url}. "
                    f"Descrição enviada pelo usuário: {caption}"
                )
            return f"Recebi uma imagem para registro. URL da imagem: {url}"

        audio = message.get("voice") or message.get("audio")
        if audio:
            self._client.send_message(chat_id, "Recebi seu áudio, estou ouvindo...")
            file_id = audio.get("file_id")
            if not file_id:
                raise RuntimeError("Áudio recebido sem file_id.")
            audio_bytes, mime = self._client.download_file(file_id)
            transcription = transcribe_audio_bytes(audio_bytes, mime).strip()
            if not transcription:
                raise RuntimeError("Não consegui transcrever o áudio.")
            return transcription

        return None


# ---------------------------------------------------------------------------
# Agent response helpers
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


def response_used_telegram_ui(messages: list) -> bool:
    """True if the agent already dispatched a native Telegram UI response."""
    recent: list = []
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "human" or type(msg).__name__ == "HumanMessage":
            break
        recent.append(msg)
    return any(
        (
            "'telegram_ui_dispatched': True" in c
            or '"telegram_ui_dispatched": True' in c
        )
        for msg in recent
        if isinstance((c := getattr(msg, "content", "")), str)
    )
