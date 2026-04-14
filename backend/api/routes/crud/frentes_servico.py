from backend.db.repository import Repository
from backend.db.session import SessionLocal

from .base import api_blueprint, _json_error, _to_dict


@api_blueprint.route("/frentes-servico", methods=["GET"])
def listar_frentes_servico():
    with SessionLocal() as db:
        frentes = Repository.frentes_servico.listar(db)
        return [_to_dict(item) for item in frentes]


@api_blueprint.route("/frentes-servico", methods=["POST"])
def criar_frente_servico():
    from flask import request

    data = request.get_json(silent=True) or {}
    try:
        nome = data["nome"]
    except KeyError as exc:
        return _json_error(f"Campo obrigatorio ausente: {exc.args[0]}")

    with SessionLocal() as db:
        frente = Repository.frentes_servico.criar(
            db,
            nome=nome,
            encarregado_responsavel=data.get("encarregado_responsavel"),
            observacao=data.get("observacao"),
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
    from flask import request

    data = request.get_json(silent=True) or {}

    with SessionLocal() as db:
        frente = Repository.frentes_servico.atualizar(
            db,
            frente_id,
            nome=data.get("nome"),
            encarregado_responsavel=data.get("encarregado_responsavel"),
            observacao=data.get("observacao"),
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
