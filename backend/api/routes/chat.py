from __future__ import annotations

from datetime import datetime
from uuid import UUID

from flask import Blueprint, g, jsonify, request
from sqlalchemy import desc, func

from backend.api.routes.auth import _is_admin, require_auth
from backend.db.models import MensagemCampo, NivelAcesso, Usuario
from backend.db.session import SessionLocal


router = Blueprint("chat_v1", __name__, url_prefix="/api/v1/chat")


def _json_error(message: str, status_code: int = 400):
    return jsonify({"ok": False, "error": message}), status_code


def _serialize_value(value):
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _parse_pagination() -> tuple[int, int, int] | tuple[None, None, tuple]:
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    if page is None or page < 1:
        return None, None, _json_error("Parâmetro 'page' deve ser inteiro >= 1.", 400)

    if per_page is None or per_page < 1:
        return None, None, _json_error("Parâmetro 'per_page' deve ser inteiro >= 1.", 400)

    per_page = min(per_page, 200)
    offset = (page - 1) * per_page
    return page, per_page, offset


# ---------------------------------------------------------------------------
# GET /api/v1/chat/conversas
# Lista todas as conversas distintas (agrupadas por telegram_chat_id),
# com info do usuário vinculado, total de mensagens e última mensagem.
# ---------------------------------------------------------------------------
@router.get("/conversas")
@require_auth
def listar_conversas():
    if not _is_admin(g.current_user):
        return _json_error("Acesso restrito a administradores.", 403)

    page, per_page, offset_or_error = _parse_pagination()
    if page is None:
        return offset_or_error

    offset = offset_or_error

    with SessionLocal() as db:
        # Subquery: última mensagem e contagem por chat_id
        subq = (
            db.query(
                MensagemCampo.telegram_chat_id,
                func.count(MensagemCampo.id).label("total_mensagens"),
                func.max(MensagemCampo.recebida_em).label("ultima_mensagem_em"),
            )
            .filter(MensagemCampo.telegram_chat_id.isnot(None))
            .group_by(MensagemCampo.telegram_chat_id)
            .subquery()
        )

        total_conversas = (
            db.query(func.count())
            .select_from(subq)
            .scalar()
        ) or 0

        rows = (
            db.query(
                subq.c.telegram_chat_id,
                subq.c.total_mensagens,
                subq.c.ultima_mensagem_em,
                Usuario.id.label("usuario_id"),
                Usuario.nome.label("usuario_nome"),
                Usuario.nivel_acesso.label("usuario_nivel_acesso"),
            )
            .outerjoin(Usuario, Usuario.telegram_chat_id == subq.c.telegram_chat_id)
            .order_by(desc(subq.c.ultima_mensagem_em))
            .offset(offset)
            .limit(per_page)
            .all()
        )

        # Para cada conversa, buscar o texto da última mensagem
        chat_ids = [r.telegram_chat_id for r in rows]
        last_msgs: dict[str, str | None] = {}
        if chat_ids:
            for chat_id in chat_ids:
                msg = (
                    db.query(MensagemCampo.texto_normalizado, MensagemCampo.texto_bruto)
                    .filter(MensagemCampo.telegram_chat_id == chat_id)
                    .order_by(desc(MensagemCampo.recebida_em))
                    .first()
                )
                if msg:
                    last_msgs[chat_id] = msg.texto_normalizado or msg.texto_bruto
                else:
                    last_msgs[chat_id] = None

        conversas = [
            {
                "telegram_chat_id": r.telegram_chat_id,
                "total_mensagens": r.total_mensagens,
                "ultima_mensagem_em": r.ultima_mensagem_em.isoformat() if r.ultima_mensagem_em else None,
                "ultima_mensagem_texto": last_msgs.get(r.telegram_chat_id),
                "usuario": {
                    "id": r.usuario_id,
                    "nome": r.usuario_nome,
                    "nivel_acesso": _serialize_value(r.usuario_nivel_acesso),
                } if r.usuario_id else None,
            }
            for r in rows
        ]

    return jsonify({
        "ok": True,
        "page": page,
        "per_page": per_page,
        "total": total_conversas,
        "conversas": conversas,
    })


def _listar_mensagens_por_chat_id(chat_id: str, page: int, per_page: int, offset: int):
    with SessionLocal() as db:
        total = (
            db.query(func.count(MensagemCampo.id))
            .filter(MensagemCampo.telegram_chat_id == chat_id)
            .scalar()
        ) or 0

        mensagens_q = (
            db.query(MensagemCampo)
            .filter(MensagemCampo.telegram_chat_id == chat_id)
            .order_by(desc(MensagemCampo.recebida_em))
            .offset(offset)
            .limit(per_page)
            .all()
        )

        mensagens = [
            {
                "id": str(m.id),
                "canal": _serialize_value(m.canal),
                "telegram_message_id": m.telegram_message_id,
                "recebida_em": m.recebida_em.isoformat() if m.recebida_em else None,
                "tipo_conteudo": _serialize_value(m.tipo_conteudo),
                "direcao": _serialize_value(m.direcao),
                "texto": m.texto_normalizado or m.texto_bruto,
                "status_processamento": _serialize_value(m.status_processamento),
                "erro_processamento": m.erro_processamento,
                "usuario_id": m.usuario_id,
            }
            for m in mensagens_q
        ]

    return jsonify({
        "ok": True,
        "telegram_chat_id": chat_id,
        "page": page,
        "per_page": per_page,
        "total": total,
        "mensagens": mensagens,
    })


# ---------------------------------------------------------------------------
# GET /api/v1/chat/mensagens?chat_id=<telegram_chat_id>
# Endpoint dedicado para mensagens de conversa (admin only).
# ---------------------------------------------------------------------------
@router.get("/mensagens")
@require_auth
def listar_mensagens_por_chat_id():
    if not _is_admin(g.current_user):
        return _json_error("Acesso restrito a administradores.", 403)

    chat_id = (request.args.get("chat_id") or "").strip()
    if not chat_id:
        return _json_error("Parâmetro obrigatório: chat_id.", 400)

    page, per_page, offset_or_error = _parse_pagination()
    if page is None:
        return offset_or_error

    return _listar_mensagens_por_chat_id(chat_id, page, per_page, offset_or_error)


# ---------------------------------------------------------------------------
# GET /api/v1/chat/conversas/<chat_id>/mensagens
# Compatibilidade com clientes antigos.
# ---------------------------------------------------------------------------
@router.get("/conversas/<chat_id>/mensagens")
@require_auth
def listar_mensagens(chat_id: str):
    if not _is_admin(g.current_user):
        return _json_error("Acesso restrito a administradores.", 403)

    page, per_page, offset_or_error = _parse_pagination()
    if page is None:
        return offset_or_error

    return _listar_mensagens_por_chat_id(chat_id, page, per_page, offset_or_error)
