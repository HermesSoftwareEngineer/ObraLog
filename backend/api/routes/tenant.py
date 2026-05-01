from flask import Blueprint, jsonify, request, g

from backend.api.routes.auth import require_auth
from backend.db.models import Tenant
from backend.db.session import SessionLocal


tenant_blueprint = Blueprint("tenant_v1", __name__, url_prefix="/api/v1/tenant")

_UPDATABLE_FIELDS = [
    "nome", "tipo_negocio",
    "cnpj", "razao_social", "nome_fantasia",
    "logradouro", "numero", "complemento", "cep", "cidade", "estado",
    "telefone_comercial", "email_comercial",
]


def _json_error(message: str, status_code: int = 400):
    return jsonify({"ok": False, "error": message}), status_code


def _tenant_payload(tenant: Tenant) -> dict:
    return {
        "ok": True,
        "tenant_id": tenant.id,
        "nome": tenant.nome,
        "slug": tenant.slug,
        "location_type": tenant.location_type,
        "tipo_negocio": tenant.tipo_negocio,
        "ativo": tenant.ativo,
        "cnpj": tenant.cnpj,
        "razao_social": tenant.razao_social,
        "nome_fantasia": tenant.nome_fantasia,
        "logradouro": tenant.logradouro,
        "numero": tenant.numero,
        "complemento": tenant.complemento,
        "cep": tenant.cep,
        "cidade": tenant.cidade,
        "estado": tenant.estado,
        "telefone_comercial": tenant.telefone_comercial,
        "email_comercial": tenant.email_comercial,
    }


def _get_tenant(tenant_id: int):
    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return None, _json_error("Tenant não encontrado.", 404)
        return tenant, None


def _apply_update(tenant_id: int, data: dict):
    location_type = data.get("location_type")
    if location_type is not None and location_type not in ["estaca", "km", "text"]:
        return None, _json_error("location_type inválido. Use 'estaca', 'km' ou 'text'.", 400)

    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return None, _json_error("Tenant não encontrado.", 404)

        if location_type is not None:
            tenant.location_type = location_type

        for field in _UPDATABLE_FIELDS:
            if field in data:
                setattr(tenant, field, data[field])

        db.commit()
        db.refresh(tenant)
        return tenant, None


# ---------------------------------------------------------------------------
# GET /api/v1/tenant  —  lê os dados da unidade do usuário autenticado
# ---------------------------------------------------------------------------

@tenant_blueprint.get("")
@require_auth
def get_unidade():
    tenant_id = getattr(g, "tenant_id", None)
    if not tenant_id:
        return _json_error("Tenant não identificado no contexto.", 403)
    tenant, err = _get_tenant(tenant_id)
    if err:
        return err
    return jsonify(_tenant_payload(tenant))


# ---------------------------------------------------------------------------
# PATCH /api/v1/tenant  —  atualiza dados da unidade (admin/gerente)
# ---------------------------------------------------------------------------

@tenant_blueprint.patch("")
@require_auth
def update_unidade():
    nivel = str(g.current_user.nivel_acesso)
    if "admin" not in nivel.lower() and "gerente" not in nivel.lower():
        return _json_error("Permissão negada. Requer perfil Admin/Gerente.", 403)

    tenant_id = getattr(g, "tenant_id", None)
    if not tenant_id:
        return _json_error("Tenant não identificado no contexto.", 403)

    data = request.get_json(silent=True) or {}
    tenant, err = _apply_update(tenant_id, data)
    if err:
        return err
    return jsonify(_tenant_payload(tenant))


# ---------------------------------------------------------------------------
# Aliases legados (mantidos para não quebrar clientes existentes)
# ---------------------------------------------------------------------------

@tenant_blueprint.get("/config")
@require_auth
def get_config():
    return get_unidade()


@tenant_blueprint.patch("/config")
@require_auth
def update_config():
    return update_unidade()

