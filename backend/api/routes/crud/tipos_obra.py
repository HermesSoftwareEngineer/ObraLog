from flask import g, request

from backend.api.routes.auth import require_auth
from backend.db.repository import TipoObraRepository
from backend.db.session import SessionLocal

from .base import api_blueprint, _json_error, _is_admin


def _check_gerente_admin():
    nivel = (
        g.current_user.nivel_acesso.value
        if hasattr(g.current_user.nivel_acesso, "value")
        else str(g.current_user.nivel_acesso)
    )
    if nivel not in ("administrador", "gerente"):
        return _json_error("Permissão negada. Requer perfil Gerente ou Administrador.", 403)
    return None


def _to_dict(t) -> dict:
    return {
        "id": t.id,
        "tenant_id": t.tenant_id,
        "slug": t.slug,
        "nome": t.nome,
        "descricao": t.descricao,
        "ativo": t.ativo,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@api_blueprint.route("/tipos-obra", methods=["GET"])
@require_auth
def listar_tipos_obra():
    tenant_id = getattr(g, "tenant_id", None)
    apenas_ativos_raw = request.args.get("apenas_ativos", "true").lower()
    apenas_ativos = apenas_ativos_raw not in ("false", "0", "no")
    with SessionLocal() as db:
        tipos = TipoObraRepository.listar(db, tenant_id, apenas_ativos=apenas_ativos)
        return [_to_dict(t) for t in tipos]


@api_blueprint.route("/tipos-obra", methods=["POST"])
@require_auth
def criar_tipo_obra():
    err = _check_gerente_admin()
    if err:
        return err

    tenant_id = getattr(g, "tenant_id", None)
    data = request.get_json(silent=True) or {}

    slug = str(data.get("slug") or "").strip().lower()
    nome = str(data.get("nome") or "").strip()
    if not slug:
        return _json_error("Campo obrigatório: slug.")
    if not nome:
        return _json_error("Campo obrigatório: nome.")
    if not slug.replace("_", "").replace("-", "").isalnum():
        return _json_error("slug deve conter apenas letras, números, hífens ou underscores.")

    with SessionLocal() as db:
        existente = TipoObraRepository.obter_por_slug(db, slug, tenant_id)
        if existente:
            return _json_error(f"Já existe um tipo de obra com slug '{slug}'.", 409)
        tipo = TipoObraRepository.criar(
            db,
            tenant_id=tenant_id,
            slug=slug,
            nome=nome,
            descricao=data.get("descricao") or None,
            ativo=bool(data.get("ativo", True)),
        )
        return _to_dict(tipo), 201


@api_blueprint.route("/tipos-obra/<int:tipo_id>", methods=["GET"])
@require_auth
def obter_tipo_obra(tipo_id: int):
    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        tipo = TipoObraRepository.obter_por_id(db, tipo_id, tenant_id)
        if not tipo:
            return _json_error("Tipo de obra não encontrado.", 404)
        return _to_dict(tipo)


@api_blueprint.route("/tipos-obra/<int:tipo_id>", methods=["PUT", "PATCH"])
@require_auth
def atualizar_tipo_obra(tipo_id: int):
    err = _check_gerente_admin()
    if err:
        return err

    tenant_id = getattr(g, "tenant_id", None)
    data = request.get_json(silent=True) or {}
    updates = {}

    if "nome" in data:
        nome = str(data["nome"] or "").strip()
        if not nome:
            return _json_error("nome não pode ser vazio.")
        updates["nome"] = nome

    if "descricao" in data:
        updates["descricao"] = str(data["descricao"] or "").strip() or None

    if "ativo" in data:
        updates["ativo"] = bool(data["ativo"])

    with SessionLocal() as db:
        tipo = TipoObraRepository.atualizar(db, tipo_id, tenant_id, **updates)
        if not tipo:
            return _json_error("Tipo de obra não encontrado.", 404)
        return _to_dict(tipo)
