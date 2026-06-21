print("[BOOT] llms.py: módulo carregando...", flush=True)
from pathlib import Path
import os
import base64
import logging

from dotenv import load_dotenv

print("[BOOT] llms.py: importando langchain_openai e langchain_google_genai...", flush=True)
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
print("[BOOT] llms.py: imports OK", flush=True)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY")
print(f"[BOOT] llms.py: DEEPSEEK_API_KEY presente={bool(deepseek_api_key)}", flush=True)
if not deepseek_api_key:
    raise RuntimeError("DEEPSEEK_API_KEY não configurada.")

google_api_key = os.environ.get("GOOGLE_API_KEY")
print(f"[BOOT] llms.py: GOOGLE_API_KEY presente={bool(google_api_key)}", flush=True)
if not google_api_key:
    raise RuntimeError("GOOGLE_API_KEY não configurada (necessária para embeddings e transcrição de áudio).")

print("[BOOT] llms.py: instanciando ChatOpenAI (DeepSeek)...", flush=True)
llm_main = ChatOpenAI(
    model="deepseek-chat",
    api_key=deepseek_api_key,
    base_url="https://api.deepseek.com",
    temperature=0.2,
    timeout=60,
    max_retries=1,
)
print("[BOOT] llms.py: ChatOpenAI (DeepSeek) instanciado OK", flush=True)

print("[BOOT] llms.py: instanciando GoogleGenerativeAIEmbeddings...", flush=True)
embeddings_model = GoogleGenerativeAIEmbeddings(
    model="models/text-embedding-004",
    google_api_key=google_api_key,
)
print("[BOOT] llms.py: GoogleGenerativeAIEmbeddings instanciado OK", flush=True)

# Modelo separado para transcrição de áudio — DeepSeek não suporta multimodal de áudio
_llm_audio = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=google_api_key,
    temperature=0,
    request_timeout=30,
    max_retries=1,
)


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
    response = _llm_audio.invoke([message])
    return _extract_text_content(response.content)
