from __future__ import annotations

import math
import logging
from pathlib import Path

from backend.agents.llms import embeddings_main
from backend.agents.instructions_store import get_instructions_path


_CHUNK_SIZE = 600
_CHUNK_OVERLAP = 120

_CHUNKS: list[str] | None = None
_VECTORS: list[list[float]] | None = None
_DISABLED_LOGGED = False
_INDEX_SOURCE_PATH: Path | None = None
_INDEX_SOURCE_MTIME: float | None = None

logger = logging.getLogger("obralog.vector_context")


def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(length, start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == length:
            break
        start = max(0, end - chunk_overlap)
    return chunks


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _ensure_index() -> None:
    global _CHUNKS, _VECTORS, _DISABLED_LOGGED, _INDEX_SOURCE_PATH, _INDEX_SOURCE_MTIME

    context_file = get_instructions_path()
    if not context_file.exists():
        _CHUNKS = []
        _VECTORS = []
        _INDEX_SOURCE_PATH = context_file
        _INDEX_SOURCE_MTIME = None
        return

    current_mtime = context_file.stat().st_mtime

    if (
        _CHUNKS is not None
        and _VECTORS is not None
        and _INDEX_SOURCE_PATH == context_file
        and _INDEX_SOURCE_MTIME == current_mtime
    ):
        return

    if embeddings_main is None:
        _CHUNKS = []
        _VECTORS = []
        if not _DISABLED_LOGGED:
            logger.warning(
                "Contexto vetorial desativado: embeddings indisponivel."
            )
            _DISABLED_LOGGED = True
        return

    content = context_file.read_text(encoding="utf-8")
    _CHUNKS = _split_text(content, _CHUNK_SIZE, _CHUNK_OVERLAP)
    try:
        _VECTORS = embeddings_main.embed_documents(_CHUNKS)
        _INDEX_SOURCE_PATH = context_file
        _INDEX_SOURCE_MTIME = current_mtime
    except Exception as exc:
        _CHUNKS = []
        _VECTORS = []
        logger.warning(
            "Falha ao indexar contexto vetorial. Seguindo sem vetor. Erro: %s",
            str(exc),
        )


def get_context_for_query(query: str, k: int = 3) -> str:
    _ensure_index()

    if not query.strip():
        return ""

    if not _CHUNKS or not _VECTORS or embeddings_main is None:
        return ""

    try:
        query_vector = embeddings_main.embed_query(query)
    except Exception as exc:
        logger.warning(
            "Falha no embed_query para contexto vetorial. Seguindo sem contexto. Erro: %s",
            str(exc),
        )
        return ""
    scored = []
    for idx, vec in enumerate(_VECTORS or []):
        score = _cosine_similarity(query_vector, vec)
        scored.append((score, idx))

    scored.sort(reverse=True)
    selected = [(_CHUNKS or [])[idx] for _, idx in scored[:k]]
    return "\n\n".join(selected).strip()
