from flask import request, g

from backend.api.routes.auth import require_auth
from backend.db.repository import Repository, RegistroSchemaRepository
from backend.db.session import SessionLocal

from .base import api_blueprint, _json_error, _to_dict


def _parse_schema_id(data: dict):
    """Extrai e converte registro_schema_id do body. Retorna (presente, valor)."""
    if "registro_schema_id" not in data:
        return False, None
    raw = data["registro_schema_id"]
    if raw in (None, ""):
        return True, None
    try:
        return True, int(raw)
    except (ValueError, TypeError):
        return None, None  # sinaliza erro


def _schema_payload(schema) -> dict:
    from .registro_schemas import _schema_to_dict
    return _schema_to_dict(schema)


@api_blueprint.route("/frentes-servico", methods=["GET"])
@require_auth
def listar_frentes_servico():
    tenant_id = getattr(g, "tenant_id", None)
    obra_filter = request.args.get("obra_id")
    nome_filter = request.args.get("nome", "").strip()
    page_raw = request.args.get("page")
    paginate = page_raw is not None

    try:
        page = max(1, int(page_raw)) if paginate else 1
        per_page = min(200, max(1, int(request.args.get("per_page", 25)))) if paginate else None
    except (ValueError, TypeError):
        return _json_error("Parametros page e per_page devem ser inteiros.")

    from backend.db.models import FrenteServico

    with SessionLocal() as db:
        q = (
            db.query(FrenteServico)
            .filter(FrenteServico.tenant_id == tenant_id)
        )

        if obra_filter:
            try:
                obra_id = int(obra_filter)
            except (ValueError, TypeError):
                return _json_error("obra_id deve ser um numero inteiro valido.")
            q = q.filter(FrenteServico.obra_id == obra_id)

        if nome_filter:
            q = q.filter(FrenteServico.nome.ilike(f"%{nome_filter}%"))

        q = q.order_by(FrenteServico.id.desc())

        if paginate:
            total = q.count()
            frentes = q.offset((page - 1) * per_page).limit(per_page).all()
            return {
                "items": [_to_dict(f) for f in frentes],
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": max(1, (total + per_page - 1) // per_page),
            }

        return [_to_dict(f) for f in q.all()]


@api_blueprint.route("/frentes-servico", methods=["POST"])
@require_auth
def criar_frente_servico():
    tenant_id = getattr(g, "tenant_id", None)
    data = request.get_json(silent=True) or {}
    try:
        nome = data["nome"]
    except KeyError as exc:
        return _json_error(f"Campo obrigatorio ausente: {exc.args[0]}")

    obra_id = data.get("obra_id")
    if obra_id in (None, ""):
        return _json_error("Campo obrigatorio ausente: obra_id.", 422)
    try:
        obra_id = int(obra_id)
    except (ValueError, TypeError):
        return _json_error("obra_id deve ser um numero inteiro valido.")

    has_schema, registro_schema_id = _parse_schema_id(data)
    if has_schema is None:
        return _json_error("registro_schema_id deve ser um numero inteiro valido.")
    if not has_schema or registro_schema_id is None:
        return _json_error("Campo obrigatorio ausente: registro_schema_id.", 422)

    with SessionLocal() as db:
        frente = Repository.frentes_servico.criar(
            db,
            nome=nome,
            encarregado_responsavel=data.get("encarregado_responsavel"),
            observacao=data.get("observacao"),
            obra_id=obra_id,
            registro_schema_id=registro_schema_id,
            tenant_id=tenant_id,
        )
        return _to_dict(frente), 201


@api_blueprint.route("/frentes-servico/<int:frente_id>", methods=["GET"])
@require_auth
def obter_frente_servico(frente_id: int):
    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        frente = Repository.frentes_servico.obter_por_id(db, frente_id, tenant_id=tenant_id)
        if not frente:
            return _json_error("Frente de servico nao encontrada.", 404)
        return _to_dict(frente)


@api_blueprint.route("/frentes-servico/<int:frente_id>", methods=["PUT", "PATCH"])
@require_auth
def atualizar_frente_servico(frente_id: int):
    tenant_id = getattr(g, "tenant_id", None)
    data = request.get_json(silent=True) or {}

    obra_id = data.get("obra_id")
    if "obra_id" in data:
        if obra_id in (None, ""):
            return _json_error("obra_id nao pode ser removido de uma frente de servico.", 422)
        try:
            obra_id = int(obra_id)
        except (ValueError, TypeError):
            return _json_error("obra_id deve ser um numero inteiro valido.")
    else:
        obra_id = None

    has_schema, registro_schema_id = _parse_schema_id(data)
    if has_schema is None:
        return _json_error("registro_schema_id deve ser um numero inteiro valido.")
    if has_schema and registro_schema_id is None:
        return _json_error("registro_schema_id nao pode ser removido de uma frente de servico.", 422)

    kwargs = {}
    if has_schema:
        kwargs["registro_schema_id"] = registro_schema_id

    with SessionLocal() as db:
        frente = Repository.frentes_servico.atualizar(
            db,
            frente_id,
            tenant_id=tenant_id,
            nome=data.get("nome"),
            encarregado_responsavel=data.get("encarregado_responsavel"),
            observacao=data.get("observacao"),
            obra_id=obra_id,
            **kwargs,
        )
        if not frente:
            return _json_error("Frente de servico nao encontrada.", 404)
        return _to_dict(frente)


@api_blueprint.route("/frentes-servico/<int:frente_id>/registro-schema", methods=["GET"])
@require_auth
def obter_registro_schema_da_frente(frente_id: int):
    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        frente = Repository.frentes_servico.obter_por_id(db, frente_id, tenant_id=tenant_id)
        if not frente:
            return _json_error("Frente de servico nao encontrada.", 404)
        if not frente.registro_schema_id:
            return _json_error("Esta frente nao possui schema de registro configurado.", 404)
        schema = RegistroSchemaRepository.obter_para_frente(db, frente_id, tenant_id)
        if not schema:
            return _json_error("Schema de registro nao encontrado.", 404)
        from .registro_schemas import _schema_to_dict
        return _schema_to_dict(schema)


@api_blueprint.route("/frentes-servico/<int:frente_id>", methods=["DELETE"])
@require_auth
def deletar_frente_servico(frente_id: int):
    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        ok = Repository.frentes_servico.deletar(db, frente_id, tenant_id=tenant_id)
        if not ok:
            return _json_error("Frente de servico nao encontrada.", 404)
        return {"ok": True}
