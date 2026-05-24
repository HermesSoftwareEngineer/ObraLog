from flask import g, request

from backend.api.routes.auth import require_auth
from backend.db.repository import Repository, RegistroSchemaRepository
from backend.db.session import SessionLocal

from .base import api_blueprint, _json_error, _to_dict


def _obra_to_dict(obra) -> dict:
    payload = _to_dict(obra)
    if obra.tipo_obra_ref:
        payload["tipo_obra_nome"] = obra.tipo_obra_ref.nome
        payload["tipo_obra_slug"] = obra.tipo_obra_ref.slug
    else:
        payload["tipo_obra_nome"] = obra.tipo_obra
        payload["tipo_obra_slug"] = obra.tipo_obra
    return payload


@api_blueprint.route("/obras", methods=["GET"])
@require_auth
def listar_obras():
    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        obras = Repository.obras.listar(db, tenant_id=tenant_id)
        return [_obra_to_dict(item) for item in obras]


@api_blueprint.route("/obras", methods=["POST"])
@require_auth
def criar_obra():
    tenant_id = getattr(g, "tenant_id", None)
    data = request.get_json(silent=True) or {}

    nome = str(data.get("nome") or "").strip()
    if not nome:
        return _json_error("Campo obrigatorio ausente: nome")

    tipo_obra_id = None
    if data.get("tipo_obra_id") not in (None, ""):
        try:
            tipo_obra_id = int(data["tipo_obra_id"])
        except (ValueError, TypeError):
            return _json_error("tipo_obra_id deve ser um número inteiro.")

    with SessionLocal() as db:
        obra = Repository.obras.criar(
            db,
            nome=nome,
            codigo=data.get("codigo"),
            descricao=data.get("descricao"),
            ativo=bool(data.get("ativo", True)),
            tipo_obra=data.get("tipo_obra") or None,
            tipo_obra_id=tipo_obra_id,
            tenant_id=tenant_id,
        )
        return _obra_to_dict(obra), 201


@api_blueprint.route("/obras/<int:obra_id>", methods=["GET"])
@require_auth
def obter_obra(obra_id: int):
    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        obra = Repository.obras.obter_por_id(db, obra_id, tenant_id=tenant_id)
        if not obra:
            return _json_error("Obra nao encontrada.", 404)
        return _obra_to_dict(obra)


@api_blueprint.route("/obras/<int:obra_id>", methods=["PUT", "PATCH"])
@require_auth
def atualizar_obra(obra_id: int):
    tenant_id = getattr(g, "tenant_id", None)
    data = request.get_json(silent=True) or {}

    tipo_obra_id = None
    if data.get("tipo_obra_id") not in (None, ""):
        try:
            tipo_obra_id = int(data["tipo_obra_id"])
        except (ValueError, TypeError):
            return _json_error("tipo_obra_id deve ser um número inteiro.")

    payload = {
        "nome": data.get("nome"),
        "codigo": data.get("codigo"),
        "descricao": data.get("descricao"),
        "ativo": data.get("ativo"),
        "tipo_obra": data.get("tipo_obra") or None,
        "tipo_obra_id": tipo_obra_id,
    }

    with SessionLocal() as db:
        obra = Repository.obras.atualizar(db, obra_id, tenant_id=tenant_id, **payload)
        if not obra:
            return _json_error("Obra nao encontrada.", 404)
        return _obra_to_dict(obra)


@api_blueprint.route("/obras/<int:obra_id>", methods=["DELETE"])
@require_auth
def deletar_obra(obra_id: int):
    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        ok = Repository.obras.deletar(db, obra_id, tenant_id=tenant_id)
        if not ok:
            return _json_error("Obra nao encontrada.", 404)
        return {"ok": True}


@api_blueprint.route("/obras/<int:obra_id>/registro-schema", methods=["GET"])
@require_auth
def obter_registro_schema_da_obra(obra_id: int):
    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        obra = Repository.obras.obter_por_id(db, obra_id, tenant_id=tenant_id)
        if not obra:
            return _json_error("Obra nao encontrada.", 404)
        if not obra.tipo_obra_id and not obra.tipo_obra:
            return _json_error("Esta obra nao possui tipo definido. Nenhum schema disponivel.", 404)
        schema = RegistroSchemaRepository.obter_ativo_para_obra(db, obra_id, tenant_id)
        if not schema:
            tipo_label = (obra.tipo_obra_ref.slug if obra.tipo_obra_ref else obra.tipo_obra) or "?"
            return _json_error(
                f"Nenhum schema ativo encontrado para tipo_obra='{tipo_label}' neste tenant.", 404
            )
        tipo_slug = schema.tipo_obra_ref.slug if schema.tipo_obra_ref else schema.tipo_obra
        tipo_nome = schema.tipo_obra_ref.nome if schema.tipo_obra_ref else schema.tipo_obra
        return {
            "id": schema.id,
            "tenant_id": schema.tenant_id,
            "tipo_obra": tipo_slug,
            "tipo_obra_id": schema.tipo_obra_id,
            "tipo_obra_nome": tipo_nome,
            "nome": schema.nome,
            "campos_ativos": schema.campos_ativos,
            "campos_extras": schema.campos_extras,
            "ativo": schema.ativo,
        }
