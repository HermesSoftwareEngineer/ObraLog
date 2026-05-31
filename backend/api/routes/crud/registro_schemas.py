from flask import g, request

from backend.api.routes.auth import require_auth
from backend.db.repository import RegistroSchemaRepository, TipoObraRepository
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


def _schema_to_dict(s) -> dict:
    tipo_slug = s.tipo_obra_ref.slug if s.tipo_obra_ref else s.tipo_obra
    tipo_nome = s.tipo_obra_ref.nome if s.tipo_obra_ref else s.tipo_obra
    return {
        "id": s.id,
        "tenant_id": s.tenant_id,
        "tipo_obra": tipo_slug,
        "tipo_obra_id": s.tipo_obra_id,
        "tipo_obra_nome": tipo_nome,
        "nome": s.nome,
        "campos_ativos": _sanitizar_campos_ativos(s.campos_ativos or {}),
        "campos_extras": s.campos_extras or [],
        "ativo": s.ativo,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _sanitizar_campos_ativos(raw: dict) -> dict:
    """Remove entradas False de campos_ativos — False significa 'não está no schema',
    que é semanticamente idêntico a não existir no dict."""
    return {campo: True for campo, ativo in raw.items() if ativo}


def _validate_campos_extras(extras) -> str | None:
    if not isinstance(extras, list):
        return "campos_extras deve ser uma lista."
    allowed_types = {"text", "number", "date", "select"}
    seen_keys = set()
    for i, campo in enumerate(extras):
        if not isinstance(campo, dict):
            return f"campos_extras[{i}]: deve ser um objeto."
        key = (campo.get("key") or "").strip()
        label = (campo.get("label") or "").strip()
        tipo = campo.get("type") or ""
        if not key:
            return f"campos_extras[{i}]: campo 'key' é obrigatório."
        if not label:
            return f"campos_extras[{i}]: campo 'label' é obrigatório."
        if tipo not in allowed_types:
            return f"campos_extras[{i}]: tipo '{tipo}' inválido. Use: {', '.join(sorted(allowed_types))}."
        if key in seen_keys:
            return f"campos_extras: chave duplicada '{key}'."
        seen_keys.add(key)
        if tipo == "select":
            options = campo.get("options")
            if not isinstance(options, list) or not options:
                return f"campos_extras[{i}] (select): 'options' deve ser uma lista não vazia."
    return None


@api_blueprint.route("/registro-schemas", methods=["GET"])
@require_auth
def listar_registro_schemas():
    err = _check_gerente_admin()
    if err:
        return err
    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        schemas = RegistroSchemaRepository.listar(db, tenant_id)
        return [_schema_to_dict(s) for s in schemas]


@api_blueprint.route("/registro-schemas", methods=["POST"])
@require_auth
def criar_registro_schema():
    err = _check_gerente_admin()
    if err:
        return err

    tenant_id = getattr(g, "tenant_id", None)
    data = request.get_json(silent=True) or {}

    nome = str(data.get("nome") or "").strip()
    if not nome:
        return _json_error("Campo obrigatório: nome.")

    tipo_obra_id = None
    tipo_obra_str = None
    if data.get("tipo_obra_id") not in (None, ""):
        try:
            tipo_obra_id = int(data["tipo_obra_id"])
        except (ValueError, TypeError):
            return _json_error("tipo_obra_id deve ser um número inteiro.")
    elif data.get("tipo_obra"):
        tipo_obra_str = str(data["tipo_obra"]).strip()

    if not tipo_obra_id and not tipo_obra_str:
        return _json_error("Campo obrigatório: tipo_obra_id ou tipo_obra.")

    campos_ativos_raw = data.get("campos_ativos") or {}
    if not isinstance(campos_ativos_raw, dict):
        return _json_error("campos_ativos deve ser um objeto {campo: bool}.")
    campos_ativos = _sanitizar_campos_ativos(campos_ativos_raw)

    campos_extras = data.get("campos_extras") or []
    validation_error = _validate_campos_extras(campos_extras)
    if validation_error:
        return _json_error(validation_error)

    with SessionLocal() as db:
        tipo_obj = None
        if tipo_obra_id:
            tipo_obj = TipoObraRepository.obter_por_id(db, tipo_obra_id, tenant_id)
            if not tipo_obj:
                return _json_error(f"tipo_obra_id {tipo_obra_id} não encontrado neste tenant.", 422)
        else:
            tipo_obj = TipoObraRepository.obter_por_slug(db, tipo_obra_str, tenant_id)
            if not tipo_obj:
                return _json_error(
                    f"Tipo de obra '{tipo_obra_str}' não encontrado. Cadastre-o em /tipos-obra primeiro.", 422
                )
            tipo_obra_id = tipo_obj.id

        tipo_obra_slug = tipo_obj.slug

        schema = RegistroSchemaRepository.criar(
            db,
            tenant_id=tenant_id,
            tipo_obra=tipo_obra_slug,
            tipo_obra_id=tipo_obra_id,
            nome=nome,
            campos_ativos=campos_ativos,
            campos_extras=campos_extras,
            ativo=bool(data.get("ativo", True)),
        )
        return _schema_to_dict(schema), 201


@api_blueprint.route("/registro-schemas/<int:schema_id>", methods=["GET"])
@require_auth
def obter_registro_schema(schema_id: int):
    err = _check_gerente_admin()
    if err:
        return err
    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        schema = RegistroSchemaRepository.obter_por_id(db, schema_id, tenant_id)
        if not schema:
            return _json_error("Schema não encontrado.", 404)
        return _schema_to_dict(schema)


@api_blueprint.route("/registro-schemas/<int:schema_id>", methods=["PUT", "PATCH"])
@require_auth
def atualizar_registro_schema(schema_id: int):
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

    if "tipo_obra" in data:
        tipo_obra = str(data["tipo_obra"] or "").strip()
        if not tipo_obra:
            return _json_error("tipo_obra não pode ser vazio.")
        updates["tipo_obra"] = tipo_obra

    if "ativo" in data:
        updates["ativo"] = bool(data["ativo"])

    if "campos_ativos" in data:
        if not isinstance(data["campos_ativos"], dict):
            return _json_error("campos_ativos deve ser um objeto {campo: bool}.")
        updates["campos_ativos"] = _sanitizar_campos_ativos(data["campos_ativos"])

    if "campos_extras" in data:
        validation_error = _validate_campos_extras(data["campos_extras"])
        if validation_error:
            return _json_error(validation_error)
        updates["campos_extras"] = data["campos_extras"]

    with SessionLocal() as db:
        schema = RegistroSchemaRepository.atualizar(db, schema_id, tenant_id, **updates)
        if not schema:
            return _json_error("Schema não encontrado.", 404)
        return _schema_to_dict(schema)


@api_blueprint.route("/registro-schemas/<int:schema_id>", methods=["DELETE"])
@require_auth
def deletar_registro_schema(schema_id: int):
    if not _is_admin(g.current_user):
        return _json_error("Apenas administrador pode excluir schemas.", 403)

    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        ok = RegistroSchemaRepository.deletar(db, schema_id, tenant_id)
        if not ok:
            return _json_error("Schema não encontrado.", 404)
        return {"ok": True}
