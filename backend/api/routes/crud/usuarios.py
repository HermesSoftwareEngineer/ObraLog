from backend.db.models import NivelAcesso
from backend.db.repository import Repository
from backend.db.session import SessionLocal

from .base import api_blueprint, _json_error, _to_dict


@api_blueprint.route("/usuarios", methods=["GET"])
def listar_usuarios():
    with SessionLocal() as db:
        usuarios = Repository.usuarios.listar(db)
        return [_to_dict(item) for item in usuarios]


@api_blueprint.route("/usuarios", methods=["POST"])
def criar_usuario():
    from flask import request

    data = request.get_json(silent=True) or {}
    try:
        nome = data["nome"]
        email = data["email"]
        senha = data["senha"]
        nivel_acesso = NivelAcesso(data.get("nivel_acesso", "encarregado"))
        telegram_chat_id = data.get("telegram_chat_id")
    except KeyError as exc:
        return _json_error(f"Campo obrigatorio ausente: {exc.args[0]}")
    except ValueError:
        return _json_error("nivel_acesso invalido.")

    with SessionLocal() as db:
        if telegram_chat_id:
            usuario = Repository.usuarios.criar_com_telegram(
                db=db,
                nome=nome,
                email=email,
                senha=senha,
                telegram_chat_id=str(telegram_chat_id),
                telegram_thread_id=str(telegram_chat_id),
                nivel_acesso=nivel_acesso,
                telefone=data.get("telefone"),
            )
        else:
            usuario = Repository.usuarios.criar(
                db=db,
                nome=nome,
                email=email,
                senha=senha,
                nivel_acesso=nivel_acesso,
                telefone=data.get("telefone"),
                telegram_thread_id=data.get("telegram_thread_id"),
            )
        return _to_dict(usuario), 201


@api_blueprint.route("/usuarios/<int:usuario_id>", methods=["GET"])
def obter_usuario(usuario_id: int):
    with SessionLocal() as db:
        usuario = Repository.usuarios.obter_por_id(db, usuario_id)
        if not usuario:
            return _json_error("Usuario nao encontrado.", 404)
        return _to_dict(usuario)


@api_blueprint.route("/usuarios/<int:usuario_id>", methods=["PUT", "PATCH"])
def atualizar_usuario(usuario_id: int):
    from flask import request

    data = request.get_json(silent=True) or {}
    update_payload = {
        "nome": data.get("nome"),
        "email": data.get("email"),
        "senha": data.get("senha"),
        "telefone": data.get("telefone"),
        "telegram_chat_id": data.get("telegram_chat_id"),
    }

    nivel_acesso = data.get("nivel_acesso")
    if nivel_acesso is not None:
        try:
            update_payload["nivel_acesso"] = NivelAcesso(nivel_acesso)
        except ValueError:
            return _json_error("nivel_acesso invalido.")

    with SessionLocal() as db:
        usuario = Repository.usuarios.atualizar(db, usuario_id, **update_payload)
        if not usuario:
            return _json_error("Usuario nao encontrado.", 404)
        return _to_dict(usuario)


@api_blueprint.route("/usuarios/<int:usuario_id>", methods=["DELETE"])
def deletar_usuario(usuario_id: int):
    with SessionLocal() as db:
        ok = Repository.usuarios.deletar(db, usuario_id)
        if not ok:
            return _json_error("Usuario nao encontrado.", 404)
        return {"ok": True}
