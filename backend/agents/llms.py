print("[BOOT] llms.py: módulo carregando...", flush=True)
from pathlib import Path
import os
import base64
import logging

from dotenv import load_dotenv

print("[BOOT] llms.py: importando langchain_google_genai...", flush=True)
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
print("[BOOT] llms.py: langchain_google_genai OK", flush=True)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

google_api_key = os.environ.get("GOOGLE_API_KEY")
print(f"[BOOT] llms.py: GOOGLE_API_KEY presente={bool(google_api_key)}", flush=True)

if not google_api_key:
    raise RuntimeError("GOOGLE_API_KEY não configurada.")

print("[BOOT] llms.py: instanciando ChatGoogleGenerativeAI...", flush=True)
# Agente principal — thinking moderado, temperatura baixa para respostas consistentes
llm_main = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash",
    google_api_key=google_api_key,
    thinking_level="medium",
    temperature=0.2,
    request_timeout=60,
    max_retries=1,
)
print("[BOOT] llms.py: ChatGoogleGenerativeAI instanciado OK", flush=True)

def _extract_text_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    parts.append(text_value)
        return "\n".join(part for part in parts if part).strip()
    if isinstance(content, dict):
        text_value = content.get("text")
        if isinstance(text_value, str):
            return text_value
    return str(content)


def transcribe_audio_bytes(audio_bytes: bytes, mime_type: str) -> str:
    encoded_audio = base64.b64encode(audio_bytes).decode("utf-8")
    message = HumanMessage(
        content=[
            {
                "type": "text",
                "text": (
                    "Transcreva fielmente este audio em portugues do Brasil. "
                    "Retorne somente a transcricao em texto simples, sem markdown e sem comentarios."
                ),
            },
            {
                "type": "media",
                "data": encoded_audio,
                "mime_type": mime_type,
            },
        ]
    )
    response = llm_main.invoke([message])
    return _extract_text_content(response.content)
