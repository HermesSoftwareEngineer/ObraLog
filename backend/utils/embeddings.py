from __future__ import annotations

from typing import Optional


def gerar_embedding(texto: str) -> Optional[list[float]]:
    """Return an embedding vector for `texto`, or None if unavailable."""
    try:
        from backend.agents.llms import embeddings_main
    except ImportError:
        try:
            from agents.llms import embeddings_main  # type: ignore[no-redef]
        except ImportError:
            return None

    if embeddings_main is None:
        return None
    try:
        return embeddings_main.embed_query(texto)
    except Exception:
        return None
