from flask import g, request

from backend.api.routes.auth import require_auth
from backend.db.repository import Repository
from backend.db.session import SessionLocal

from .base import api_blueprint, _json_error, _to_dict


@api_blueprint.route("/obras", methods=["GET"])
@require_auth
def listar_obras():
    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        obras = Repository.obras.listar(db, tenant_id=tenant_id)
        return [_to_dict(item) for item in obras]


@api_blueprint.route("/obras", methods=["POST"])
@require_auth
def criar_obra():
    tenant_id = getattr(g, "tenant_id", None)
    data = request.get_json(silent=True) or {}

    nome = str(data.get("nome") or "").strip()
    if not nome:
        return _json_error("Campo obrigatorio ausente: nome")

    with SessionLocal() as db:
        obra = Repository.obras.criar(
            db,
            nome=nome,
            codigo=data.get("codigo"),
            descricao=data.get("descricao"),
            ativo=bool(data.get("ativo", True)),
            tenant_id=tenant_id,
        )
        return _to_dict(obra), 201


@api_blueprint.route("/obras/<int:obra_id>", methods=["GET"])
@require_auth
def obter_obra(obra_id: int):
    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        obra = Repository.obras.obter_por_id(db, obra_id, tenant_id=tenant_id)
        if not obra:
            return _json_error("Obra nao encontrada.", 404)
        return _to_dict(obra)


@api_blueprint.route("/obras/<int:obra_id>", methods=["PUT", "PATCH"])
@require_auth
def atualizar_obra(obra_id: int):
    tenant_id = getattr(g, "tenant_id", None)
    data = request.get_json(silent=True) or {}

    payload = {
        "nome": data.get("nome"),
        "codigo": data.get("codigo"),
        "descricao": data.get("descricao"),
        "ativo": data.get("ativo"),
    }

    with SessionLocal() as db:
        obra = Repository.obras.atualizar(db, obra_id, tenant_id=tenant_id, **payload)
        if not obra:
            return _json_error("Obra nao encontrada.", 404)
        return _to_dict(obra)


@api_blueprint.route("/obras/<int:obra_id>", methods=["DELETE"])
@require_auth
def deletar_obra(obra_id: int):
    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        ok = Repository.obras.deletar(db, obra_id, tenant_id=tenant_id)
        if not ok:
            return _json_error("Obra nao encontrada.", 404)
        return {"ok": True}
