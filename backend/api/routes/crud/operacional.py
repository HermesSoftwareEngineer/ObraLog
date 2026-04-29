from backend.api.routes.auth import require_auth
from backend.db.models import MensagemCampo
from backend.db.repository import Repository
from backend.db.session import SessionLocal

from .base import (
    api_blueprint,
    _json_error,
    _parse_processamento_status,
    _parse_uuid,
    _serialize_mensagem_campo,
    _to_dict,
)


@api_blueprint.route("/mensagens-campo", methods=["GET"])
@require_auth
def listar_mensagens_campo():
    from flask import request

    status = request.args.get("status")
    telegram_chat_id = request.args.get("telegram_chat_id")
    limit_raw = request.args.get("limit") or "50"

    try:
        limit = max(1, min(int(limit_raw), 200))
    except Exception:
        return _json_error("Parametro invalido: limit. Use numero inteiro.", 422)

    with SessionLocal() as db:
        query = db.query(MensagemCampo)
        if status:
            try:
                status_norm = _parse_processamento_status(status)
            except ValueError as exc:
                return _json_error(str(exc), 422)
            query = query.filter(MensagemCampo.status_processamento == status_norm)

        if telegram_chat_id:
            query = query.filter(MensagemCampo.telegram_chat_id == str(telegram_chat_id))

        items = query.order_by(MensagemCampo.recebida_em.desc()).limit(limit).all()
        return {"ok": True, "total": len(items), "items": [_serialize_mensagem_campo(item) for item in items]}


@api_blueprint.route("/mensagens-campo/<string:mensagem_id>", methods=["GET"])
@require_auth
def obter_mensagem_campo(mensagem_id: str):
    try:
        parsed_id = _parse_uuid(mensagem_id, "mensagem_id")
    except ValueError as exc:
        return _json_error(str(exc), 422)

    with SessionLocal() as db:
        item = db.query(MensagemCampo).filter(MensagemCampo.id == parsed_id).first()
        if not item:
            return _json_error("Mensagem nao encontrada.", 404)
        return {"ok": True, "item": _serialize_mensagem_campo(item)}
