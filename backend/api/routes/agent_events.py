"""SSE endpoint: streams new agent messages for a conversation to the frontend.

GET /api/v1/agent/events/<chat_id>?since=<iso_timestamp>

The frontend connects once after sending a message and receives new MensagemCampo
entries (direction=agent) as they are persisted by the worker.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from flask import Blueprint, Response, g, request, stream_with_context
from sqlalchemy import desc

from backend.api.routes.auth import require_auth
from backend.db.models import DirecaoMensagem, MensagemCampo
from backend.db.session import SessionLocal

router = Blueprint("agent_events", __name__, url_prefix="/api/v1/agent")

_POLL_INTERVAL = 1.5   # seconds between DB polls
_KEEPALIVE_EVERY = 15  # seconds between keepalive comments


def _serialize_msg(m: MensagemCampo) -> dict:
    return {
        "id": str(m.id),
        "direcao": m.direcao.value if hasattr(m.direcao, "value") else str(m.direcao),
        "texto": m.texto_normalizado or m.texto_bruto or "",
        "recebida_em": m.recebida_em.isoformat() if m.recebida_em else None,
        "status": m.status_processamento.value if hasattr(m.status_processamento, "value") else str(m.status_processamento),
    }


def _fetch_new_messages(chat_id: str, since: datetime) -> list[dict]:
    with SessionLocal() as db:
        rows = (
            db.query(MensagemCampo)
            .filter(
                MensagemCampo.telegram_chat_id == chat_id,
                MensagemCampo.direcao == DirecaoMensagem.AGENT,
                MensagemCampo.recebida_em > since,
            )
            .order_by(MensagemCampo.recebida_em)
            .limit(20)
            .all()
        )
        return [_serialize_msg(m) for m in rows]


@router.get("/events/<path:chat_id>")
@require_auth
def stream_events(chat_id: str):
    """Stream agent reply events for a conversation via SSE."""
    since_str = (request.args.get("since") or "").strip()
    try:
        since = datetime.fromisoformat(since_str) if since_str else datetime.now(tz=timezone.utc)
    except ValueError:
        since = datetime.now(tz=timezone.utc)

    def event_stream():
        nonlocal since
        last_keepalive = time.monotonic()

        while True:
            msgs = _fetch_new_messages(chat_id, since)
            for msg in msgs:
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                # Advance the cursor to the latest message timestamp
                ts_str = msg.get("recebida_em")
                if ts_str:
                    try:
                        since = datetime.fromisoformat(ts_str)
                    except ValueError:
                        pass

            now = time.monotonic()
            if now - last_keepalive >= _KEEPALIVE_EVERY:
                yield ": keepalive\n\n"
                last_keepalive = now

            time.sleep(_POLL_INTERVAL)

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # desabilita buffer do Nginx
            "Connection": "keep-alive",
        },
    )
