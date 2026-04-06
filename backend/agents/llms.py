from pathlib import Path
import os
import base64
import logging
from typing import Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logger = logging.getLogger("obralog.embeddings")

google_api_key = os.environ.get("GOOGLE_API_KEY")

if not google_api_key:
    raise RuntimeError("GOOGLE_API_KEY não configurada.")

llm_main = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=google_api_key,
)


def _build_embeddings_client() -> Optional[GoogleGenerativeAIEmbeddings]:
    preferred_model = os.environ.get(
        "GOOGLE_EMBEDDING_MODEL",
        "models/text-multilingual-embedding-002",
    ).strip()
    candidates = [
        preferred_model,
        "models/text-multilingual-embedding-002",
        "models/text-embedding-004",
        "models/gemini-embedding-2-preview",
        "models/gemini-embedding-001",
        "models/embedding-001",
    ]
    seen = set()

    for model_name in candidates:
        if not model_name or model_name in seen:
            continue
        seen.add(model_name)
        try:
            client = GoogleGenerativeAIEmbeddings(
                model=model_name,
                google_api_key=google_api_key,
            )
            client.embed_query("teste de embedding")
            logger.info("Embeddings habilitado com modelo: %s", model_name)
            return client
        except Exception as exc:
            msg = str(exc)
            if "NOT_FOUND" in msg or "404" in msg:
                logger.debug("Modelo '%s' indisponivel na API atual (404).", model_name)
            else:
                logger.warning(
                    "Falha ao inicializar embedding model '%s': %s",
                    model_name,
                    msg,
                )
            continue

    logger.error(
        "Embeddings desabilitado: nenhum modelo de embedding disponivel para a chave/API atual. "
        "O agente vai continuar sem contexto vetorial."
    )
    return None


embeddings_main = _build_embeddings_client()


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
