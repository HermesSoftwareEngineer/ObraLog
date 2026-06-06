print("[BOOT] admin.py: módulo carregando...", flush=True)
import re

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from backend.api.routes.auth import _is_admin, _issue_token, require_auth
from backend.db.models import Tenant
from backend.db.session import SessionLocal


admin_blueprint = Blueprint("admin_v1", __name__, url_prefix="/api/v1/admin")

_UPDATABLE_FIELDS = [
    "nome", "tipo_negocio", "ativo",
    "cnpj", "razao_social", "nome_fantasia",
    "logradouro", "numero", "complemento", "cep", "cidade", "estado",
    "telefone_comercial", "email_comercial",
]


def _json_error(message: str, status_code: int = 400):
    return jsonify({"ok": False, "error": message}), status_code


def _serialize_tenant(t) -> dict:
    return {
        "id": t.id,
        "nome": t.nome,
        "slug": t.slug,
        "ativo": t.ativo,
        "tipo_negocio": t.tipo_negocio,
        "cnpj": t.cnpj,
        "razao_social": t.razao_social,
        "nome_fantasia": t.nome_fantasia,
        "logradouro": t.logradouro,
        "numero": t.numero,
        "complemento": t.complemento,
        "cep": t.cep,
        "cidade": t.cidade,
        "estado": t.estado,
        "telefone_comercial": t.telefone_comercial,
        "email_comercial": t.email_comercial,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[àáâãäå]", "a", text)
    text = re.sub(r"[èéêë]", "e", text)
    text = re.sub(r"[ìíîï]", "i", text)
    text = re.sub(r"[òóôõö]", "o", text)
    text = re.sub(r"[ùúûü]", "u", text)
    text = re.sub(r"[ç]", "c", text)
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


# ---------------------------------------------------------------------------
# GET /api/v1/admin/tenants
# ---------------------------------------------------------------------------

@admin_blueprint.get("/tenants")
@require_auth
def listar_tenants():
    if not _is_admin(g.current_user):
        return _json_error("Apenas administrador pode listar unidades.", 403)

    status_filter = request.args.get("status", "all")

    with SessionLocal() as db:
        query = db.query(Tenant).order_by(Tenant.nome)
        if status_filter == "ativo":
            query = query.filter(Tenant.ativo.is_(True))
        elif status_filter == "inativo":
            query = query.filter(Tenant.ativo.is_(False))
        tenants = query.all()
        result = [_serialize_tenant(t) for t in tenants]

    return jsonify({"ok": True, "tenants": result})


# ---------------------------------------------------------------------------
# POST /api/v1/admin/tenants
# ---------------------------------------------------------------------------

@admin_blueprint.post("/tenants")
@require_auth
def criar_tenant():
    if not _is_admin(g.current_user):
        return _json_error("Apenas administrador pode criar unidades.", 403)

    data = request.get_json(silent=True) or {}
    nome = str(data.get("nome") or "").strip()
    if not nome:
        return _json_error("Campo obrigatório ausente: nome.")

    slug = str(data.get("slug") or "").strip() or _slugify(nome)
    if not slug:
        return _json_error("Slug inválido.")

    try:
        with SessionLocal() as db:
            tenant = Tenant(
                nome=nome,
                slug=slug,
                tipo_negocio=data.get("tipo_negocio") or None,
                ativo=bool(data.get("ativo", True)),
                cnpj=data.get("cnpj") or None,
                razao_social=data.get("razao_social") or None,
                nome_fantasia=data.get("nome_fantasia") or None,
                logradouro=data.get("logradouro") or None,
                numero=data.get("numero") or None,
                complemento=data.get("complemento") or None,
                cep=data.get("cep") or None,
                cidade=data.get("cidade") or None,
                estado=(data.get("estado") or "").upper()[:2] or None,
                telefone_comercial=data.get("telefone_comercial") or None,
                email_comercial=data.get("email_comercial") or None,
            )
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            return jsonify({"ok": True, "tenant": _serialize_tenant(tenant)}), 201
    except IntegrityError:
        return _json_error(f"Slug '{slug}' já está em uso. Escolha outro.", 409)


# ---------------------------------------------------------------------------
# GET /api/v1/admin/tenants/<id>
# ---------------------------------------------------------------------------

@admin_blueprint.get("/tenants/<int:tenant_id>")
@require_auth
def obter_tenant(tenant_id: int):
    if not _is_admin(g.current_user):
        return _json_error("Apenas administrador pode visualizar unidades.", 403)

    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return _json_error("Unidade não encontrada.", 404)
        return jsonify({"ok": True, "tenant": _serialize_tenant(tenant)})


# ---------------------------------------------------------------------------
# PUT /api/v1/admin/tenants/<id>
# ---------------------------------------------------------------------------

@admin_blueprint.put("/tenants/<int:tenant_id>")
@require_auth
def atualizar_tenant(tenant_id: int):
    if not _is_admin(g.current_user):
        return _json_error("Apenas administrador pode editar unidades.", 403)

    data = request.get_json(silent=True) or {}

    try:
        with SessionLocal() as db:
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if not tenant:
                return _json_error("Unidade não encontrada.", 404)

            for field in _UPDATABLE_FIELDS:
                if field not in data:
                    continue
                value = data[field]
                if field == "estado" and value:
                    value = str(value).upper()[:2]
                elif field in ("nome", "tipo_negocio", "cnpj", "razao_social",
                               "nome_fantasia", "logradouro", "numero",
                               "complemento", "cep", "cidade",
                               "telefone_comercial", "email_comercial"):
                    value = str(value).strip() or None
                setattr(tenant, field, value)

            db.commit()
            db.refresh(tenant)
            return jsonify({"ok": True, "tenant": _serialize_tenant(tenant)})
    except IntegrityError:
        return _json_error("Conflito ao salvar. Verifique os dados.", 409)


# ---------------------------------------------------------------------------
# DELETE /api/v1/admin/tenants/<id>  — desativa (soft delete)
# ---------------------------------------------------------------------------

@admin_blueprint.delete("/tenants/<int:tenant_id>")
@require_auth
def deletar_tenant(tenant_id: int):
    if not _is_admin(g.current_user):
        return _json_error("Apenas administrador pode excluir unidades.", 403)

    with SessionLocal() as db:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            return _json_error("Unidade não encontrada.", 404)
        tenant.ativo = False
        db.commit()
        return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# POST /api/v1/admin/switch-tenant
# ---------------------------------------------------------------------------

@admin_blueprint.post("/switch-tenant")
@require_auth
def switch_tenant():
    if not _is_admin(g.current_user):
        return _json_error("Apenas administrador pode alternar unidade.", 403)

    data = request.get_json(silent=True) or {}
    target_id = data.get("tenant_id")
    if not target_id:
        return _json_error("Campo obrigatório: tenant_id.")

    with SessionLocal() as db:
        tenant = (
            db.query(Tenant)
            .filter(Tenant.id == int(target_id), Tenant.ativo.is_(True))
            .first()
        )
        if not tenant:
            return _json_error("Unidade não encontrada.", 404)
        tenant_data = {"id": tenant.id, "nome": tenant.nome, "slug": tenant.slug}

    token = _issue_token(g.current_user.id, g.current_user.email, int(target_id))
    return jsonify({"ok": True, "token": token, "tenant": tenant_data})
