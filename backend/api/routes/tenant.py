from flask import Blueprint, jsonify, request, g

from backend.api.routes.auth import require_auth
from backend.db.models import Tenant
from backend.db.session import SessionLocal


tenant_blueprint = Blueprint("tenant_v1", __name__, url_prefix="/api/v1/tenant")


def _json_error(message: str, status_code: int = 400):
    return jsonify({"ok": False, "error": message}), status_code


@tenant_blueprint.get("/config")
@require_auth
def get_config():
    tenant_id = getattr(g, "tenant_id", None)
    if not tenant_id:
        return _json_error("Tenant não identificado no contexto.", 403)

    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return _json_error("Tenant não encontrado.", 404)

        return jsonify(
            {
                "ok": True,
                "tenant_id": tenant.id,
                "nome": tenant.nome,
                "location_type": tenant.location_type,
                "tipo_negocio": tenant.tipo_negocio,
            }
        )


@tenant_blueprint.patch("/config")
@require_auth
def update_config():
    nivel = str(g.current_user.nivel_acesso)
    if "admin" not in nivel.lower() and "gerente" not in nivel.lower():
        return _json_error("Permissão negada. Requer perfil Admin/Gerente.", 403)

    tenant_id = getattr(g, "tenant_id", None)
    if not tenant_id:
        return _json_error("Tenant não identificado no contexto.", 403)

    data = request.get_json(silent=True) or {}
    location_type = data.get("location_type")

    if location_type not in ["estaca", "km", "text"]:
        return _json_error("location_type inválido. Use 'estaca', 'km' ou 'text'.", 400)

    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return _json_error("Tenant não encontrado.", 404)

        tenant.location_type = location_type
        db.commit()
        db.refresh(tenant)

        return jsonify({"ok": True, "location_type": tenant.location_type})
