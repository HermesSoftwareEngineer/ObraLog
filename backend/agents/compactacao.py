"""Compactação de conversas: resumo LLM + documento enriquecido + embedding pgvector.

Dois modos de uso:
  1. Ao encerrar a conversa — persiste resumo + embedding, sem compressão de state.
  2. Mid-conversation (> 50k tokens) — persiste + retorna mensagens comprimidas para
     substituir o state do LangGraph (mantém os últimos KEEP_RECENT_PAIRS pares).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from sqlalchemy.orm import Session

logger = logging.getLogger("obralog.agents.compactacao")

TOKEN_THRESHOLD = 50_000
_KEEP_RECENT_PAIRS = 6   # pares human/AI preservados após compactação
_MAX_TRANSCRIPT_CHARS = 14_000  # ~3.5k tokens enviados ao LLM para gerar o resumo


# ---------------------------------------------------------------------------
# Estimativa de tokens
# ---------------------------------------------------------------------------

def estimate_tokens(messages: list[BaseMessage]) -> int:
    """Rough estimate: len(chars) / 4."""
    total = 0
    for msg in messages:
        content = getattr(msg, "content", "") or ""
        if isinstance(content, str):
            total += len(content) // 4
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, str):
                    total += len(item) // 4
                elif isinstance(item, dict):
                    total += len(str(item.get("text", ""))) // 4
    return total


def needs_compaction(messages: list[BaseMessage]) -> bool:
    return estimate_tokens(messages) > TOKEN_THRESHOLD


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------

def _build_transcript(messages: list[BaseMessage]) -> str:
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, (SystemMessage, ToolMessage)):
            continue
        if isinstance(msg, HumanMessage):
            role = "Usuário"
        elif isinstance(msg, AIMessage):
            role = "Agente"
        else:
            continue
        content = getattr(msg, "content", "") or ""
        if isinstance(content, list):
            text = " ".join(
                item if isinstance(item, str) else item.get("text", "")
                for item in content
                if isinstance(item, (str, dict))
            ).strip()
        else:
            text = str(content).strip()
        if text:
            parts.append(f"{role}: {text}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# LLM — resumo e entidades
# ---------------------------------------------------------------------------

def _gerar_resumo_e_entidades(transcript: str) -> tuple[str, str]:
    try:
        from backend.agents.llms import llm_main, _extract_text_content
    except ImportError:
        from agents.llms import llm_main, _extract_text_content  # type: ignore

    prompt = (
        "Você recebeu a transcrição de uma conversa operacional de um app de construção civil.\n\n"
        "TAREFA 1 — RESUMO:\n"
        "Escreva um resumo em português (2-4 parágrafos) capturando: o que foi discutido, "
        "decisões tomadas, tarefas concluídas e pendências em aberto.\n\n"
        "TAREFA 2 — ENTIDADES:\n"
        "Extraia em uma linha: obras mencionadas, frentes de serviço, nomes de funcionários, "
        "datas específicas, volumes/quantidades relevantes.\n"
        'Formato: "ENTIDADES | obras: X | frentes: Y | funcionários: Z | datas: W | valores: V"\n\n'
        f"TRANSCRIÇÃO:\n{transcript[:_MAX_TRANSCRIPT_CHARS]}\n\n"
        "Responda exatamente neste formato:\n"
        "RESUMO:\n<resumo>\n\nENTIDADES:\n<linha de entidades>"
    )

    response = llm_main.invoke([HumanMessage(content=prompt)])
    raw = _extract_text_content(response.content)

    resumo = raw.strip()
    entidades = ""

    if "RESUMO:" in raw and "ENTIDADES:" in raw:
        partes = raw.split("ENTIDADES:", 1)
        entidades = partes[1].strip()
        resumo = partes[0].replace("RESUMO:", "").strip()
    elif "ENTIDADES:" in raw:
        partes = raw.split("ENTIDADES:", 1)
        entidades = partes[1].strip()
        resumo = partes[0].strip()

    return resumo, entidades


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def _gerar_embedding(texto: str) -> list[float] | None:
    try:
        from backend.agents.llms import embeddings_model
    except ImportError:
        try:
            from agents.llms import embeddings_model  # type: ignore
        except ImportError:
            return None
    try:
        return embeddings_model.embed_query(texto)
    except Exception as exc:
        logger.warning("[COMPACTACAO] Falha ao gerar embedding: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

def _persistir(
    db: Session,
    conversa_id: int,
    resumo: str,
    documento_enriquecido: str,
    embedding: list[float] | None,
) -> None:
    from sqlalchemy import text

    db.execute(
        text("UPDATE conversas SET resumo = :r WHERE id = :id"),
        {"r": resumo[:4000], "id": conversa_id},
    )

    if embedding is not None:
        emb_str = "[" + ",".join(str(v) for v in embedding) + "]"
        db.execute(
            text(
                "INSERT INTO conversa_resumos (conversa_id, resumo, documento_enriquecido, embedding) "
                "VALUES (:cid, :resumo, :doc, :emb::vector)"
            ),
            {"cid": conversa_id, "resumo": resumo, "doc": documento_enriquecido, "emb": emb_str},
        )
    else:
        db.execute(
            text(
                "INSERT INTO conversa_resumos (conversa_id, resumo, documento_enriquecido) "
                "VALUES (:cid, :resumo, :doc)"
            ),
            {"cid": conversa_id, "resumo": resumo, "doc": documento_enriquecido},
        )

    db.commit()


# ---------------------------------------------------------------------------
# Compressão de state
# ---------------------------------------------------------------------------

def _compress_messages(messages: list[BaseMessage], resumo: str) -> list[BaseMessage]:
    """Keep the last _KEEP_RECENT_PAIRS human/AI pairs; prepend a summary marker."""
    human_indices = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    if len(human_indices) <= _KEEP_RECENT_PAIRS:
        return messages

    cutoff = human_indices[-_KEEP_RECENT_PAIRS]
    recent = messages[cutoff:]
    summary_msg = SystemMessage(
        content=f"[RESUMO DO HISTÓRICO ANTERIOR]\n{resumo}\n[FIM DO RESUMO]"
    )
    return [summary_msg] + recent


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def compactar_conversa(
    db: Session,
    conversa_id: int,
    messages: list[BaseMessage] | None = None,
    compress_state: bool = False,
) -> tuple[str | None, list[BaseMessage] | None]:
    """
    Gera resumo, persiste em conversa_resumos e opcionalmente comprime o state.

    Args:
        db: Session SQLAlchemy ativa.
        conversa_id: ID da conversa a compactar.
        messages: Lista de mensagens do state LangGraph (necessário para gerar o transcript).
        compress_state: Se True, retorna lista de mensagens comprimidas.

    Returns:
        (resumo, compressed_messages) onde compressed_messages é None se compress_state=False.
    """
    if not messages:
        logger.warning("[COMPACTACAO] Sem mensagens para compactar conversa_id=%d", conversa_id)
        return None, None

    transcript = _build_transcript(messages)
    if not transcript.strip():
        return None, None

    logger.info(
        "[COMPACTACAO] Gerando resumo conversa_id=%d chars=%d",
        conversa_id, len(transcript),
    )

    resumo, entidades = _gerar_resumo_e_entidades(transcript)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    documento = f"[RESUMO] {resumo}\n[ENTIDADES] {entidades}\n[COMPACTADO_EM] {now_str}"

    embedding = _gerar_embedding(documento)
    _persistir(db, conversa_id, resumo, documento, embedding)

    logger.info(
        "[COMPACTACAO] Persistido conversa_id=%d embedding=%s",
        conversa_id, embedding is not None,
    )

    compressed = _compress_messages(messages, resumo) if compress_state else None
    return resumo, compressed


def compactar_conversa_async(conversa_id: int, messages: list[BaseMessage]) -> None:
    """Fire-and-forget: compacta em background thread sem comprimir state."""
    def _run() -> None:
        try:
            from backend.db.session import SessionLocal
        except ImportError:
            from db.session import SessionLocal  # type: ignore
        try:
            with SessionLocal() as db:
                compactar_conversa(db, conversa_id, messages, compress_state=False)
        except Exception as exc:
            logger.error("[COMPACTACAO] Erro em background conversa_id=%d: %s", conversa_id, exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
