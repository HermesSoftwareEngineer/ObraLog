from flask import request

from backend.db.models import NivelAcesso, Obra, Tenant
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

    obra_id = None
    if data.get("obra_id") not in (None, ""):
        try:
            obra_id = int(data["obra_id"])
        except (ValueError, TypeError):
            return _json_error("obra_id deve ser um numero inteiro.")

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

        if obra_id:
            obra = db.query(Obra).filter(Obra.id == obra_id).first()
            if obra:
                Repository.usuario_obras.associar(db, usuario.id, obra_id, obra.tenant_id, eh_padrao=True)

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


# ---------------------------------------------------------------------------
# Obras do usuário
# ---------------------------------------------------------------------------

@api_blueprint.route("/usuarios/<int:usuario_id>/obras", methods=["GET"])
def listar_obras_do_usuario(usuario_id: int):
    with SessionLocal() as db:
        usuario = Repository.usuarios.obter_por_id(db, usuario_id)
        if not usuario:
            return _json_error("Usuario nao encontrado.", 404)
        obras = Repository.usuario_obras.listar_obras_do_usuario(db, usuario_id, usuario.tenant_id)
        return obras


@api_blueprint.route("/usuarios/<int:usuario_id>/obras", methods=["POST"])
def associar_obra_ao_usuario(usuario_id: int):
    data = request.get_json(silent=True) or {}
    obra_id = data.get("obra_id")
    if not obra_id:
        return _json_error("Campo obrigatorio: obra_id.")

    with SessionLocal() as db:
        usuario = Repository.usuarios.obter_por_id(db, usuario_id)
        if not usuario:
            return _json_error("Usuario nao encontrado.", 404)
        obra = db.query(Obra).filter(Obra.id == int(obra_id)).first()
        if not obra:
            return _json_error("Obra nao encontrada.", 404)
        uo = Repository.usuario_obras.associar(
            db, usuario_id, int(obra_id), obra.tenant_id
        )
        return {"ok": True, "obra_id": uo.obra_id, "eh_padrao": uo.eh_padrao}, 201


@api_blueprint.route("/usuarios/<int:usuario_id>/obras/<int:obra_id>", methods=["DELETE"])
def desassociar_obra_do_usuario(usuario_id: int, obra_id: int):
    with SessionLocal() as db:
        usuario = Repository.usuarios.obter_por_id(db, usuario_id)
        if not usuario:
            return _json_error("Usuario nao encontrado.", 404)
        ok = Repository.usuario_obras.desassociar(db, usuario_id, obra_id, usuario.tenant_id)
        if not ok:
            return _json_error("Associacao nao encontrada.", 404)
        return {"ok": True}


@api_blueprint.route("/usuarios/<int:usuario_id>/obras/<int:obra_id>/padrao", methods=["PATCH"])
def definir_obra_padrao_do_usuario(usuario_id: int, obra_id: int):
    with SessionLocal() as db:
        usuario = Repository.usuarios.obter_por_id(db, usuario_id)
        if not usuario:
            return _json_error("Usuario nao encontrado.", 404)
        ok = Repository.usuario_obras.definir_padrao(db, usuario_id, obra_id, usuario.tenant_id)
        if not ok:
            return _json_error("Associacao nao encontrada.", 404)
        return {"ok": True}


# ---------------------------------------------------------------------------
# Tenants do usuário (admins multi-tenant)
# ---------------------------------------------------------------------------

@api_blueprint.route("/usuarios/<int:usuario_id>/tenants", methods=["GET"])
def listar_tenants_do_usuario(usuario_id: int):
    with SessionLocal() as db:
        usuario = Repository.usuarios.obter_por_id(db, usuario_id)
        if not usuario:
            return _json_error("Usuario nao encontrado.", 404)
        tenants = Repository.usuario_tenants.listar_tenants_do_usuario(db, usuario_id)
        return tenants


@api_blueprint.route("/usuarios/<int:usuario_id>/tenants", methods=["POST"])
def associar_tenant_ao_usuario(usuario_id: int):
    data = request.get_json(silent=True) or {}
    tenant_id = data.get("tenant_id")
    if not tenant_id:
        return _json_error("Campo obrigatorio: tenant_id.")

    with SessionLocal() as db:
        usuario = Repository.usuarios.obter_por_id(db, usuario_id)
        if not usuario:
            return _json_error("Usuario nao encontrado.", 404)
        tenant = db.query(Tenant).filter(Tenant.id == int(tenant_id)).first()
        if not tenant:
            return _json_error("Tenant nao encontrado.", 404)
        ut = Repository.usuario_tenants.associar(db, usuario_id, int(tenant_id))
        return {"ok": True, "tenant_id": ut.tenant_id, "eh_padrao": ut.eh_padrao}, 201


@api_blueprint.route("/usuarios/<int:usuario_id>/tenants/<int:tenant_id>", methods=["DELETE"])
def desassociar_tenant_do_usuario(usuario_id: int, tenant_id: int):
    with SessionLocal() as db:
        usuario = Repository.usuarios.obter_por_id(db, usuario_id)
        if not usuario:
            return _json_error("Usuario nao encontrado.", 404)
        ok = Repository.usuario_tenants.desassociar(db, usuario_id, tenant_id)
        if not ok:
            return _json_error("Associacao nao encontrada.", 404)
        return {"ok": True}


@api_blueprint.route("/usuarios/<int:usuario_id>/tenants/<int:tenant_id>/padrao", methods=["PATCH"])
def definir_tenant_padrao_do_usuario(usuario_id: int, tenant_id: int):
    with SessionLocal() as db:
        usuario = Repository.usuarios.obter_por_id(db, usuario_id)
        if not usuario:
            return _json_error("Usuario nao encontrado.", 404)
        ok = Repository.usuario_tenants.definir_padrao(db, usuario_id, tenant_id)
        if not ok:
            return _json_error("Associacao nao encontrada.", 404)
        return {"ok": True}
