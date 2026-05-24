from flask import request, g

from backend.db.repository import Repository
from backend.db.session import SessionLocal

from .base import api_blueprint, _json_error, _to_dict


@api_blueprint.route("/frentes-servico", methods=["GET"])
def listar_frentes_servico():
    tenant_id = getattr(g, "tenant_id", None)
    obra_filter = request.args.get("obra_id")
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
def criar_frente_servico():
    data = request.get_json(silent=True) or {}
    try:
        nome = data["nome"]
    except KeyError as exc:
        return _json_error(f"Campo obrigatorio ausente: {exc.args[0]}")

    obra_id = data.get("obra_id")
    if obra_id not in (None, ""):
        try:
            obra_id = int(obra_id)
        except (ValueError, TypeError):
            return _json_error("obra_id deve ser um numero inteiro valido.")
    else:
        obra_id = None

    with SessionLocal() as db:
        frente = Repository.frentes_servico.criar(
            db,
            nome=nome,
            encarregado_responsavel=data.get("encarregado_responsavel"),
            observacao=data.get("observacao"),
            obra_id=obra_id,
        )
        return _to_dict(frente), 201


@api_blueprint.route("/frentes-servico/<int:frente_id>", methods=["GET"])
def obter_frente_servico(frente_id: int):
    with SessionLocal() as db:
        frente = Repository.frentes_servico.obter_por_id(db, frente_id)
        if not frente:
            return _json_error("Frente de servico nao encontrada.", 404)
        return _to_dict(frente)


@api_blueprint.route("/frentes-servico/<int:frente_id>", methods=["PUT", "PATCH"])
def atualizar_frente_servico(frente_id: int):
    data = request.get_json(silent=True) or {}

    obra_id = data.get("obra_id")
    if obra_id not in (None, ""):
        try:
            obra_id = int(obra_id)
        except (ValueError, TypeError):
            return _json_error("obra_id deve ser um numero inteiro valido.")
    else:
        obra_id = None

    with SessionLocal() as db:
        frente = Repository.frentes_servico.atualizar(
            db,
            frente_id,
            nome=data.get("nome"),
            encarregado_responsavel=data.get("encarregado_responsavel"),
            observacao=data.get("observacao"),
            obra_id=obra_id,
        )
        if not frente:
            return _json_error("Frente de servico nao encontrada.", 404)
        return _to_dict(frente)


@api_blueprint.route("/frentes-servico/<int:frente_id>", methods=["DELETE"])
def deletar_frente_servico(frente_id: int):
    with SessionLocal() as db:
        ok = Repository.frentes_servico.deletar(db, frente_id)
        if not ok:
            return _json_error("Frente de servico nao encontrada.", 404)
        return {"ok": True}
