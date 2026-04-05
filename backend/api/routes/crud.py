from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

from flask import Blueprint, jsonify, request

from backend.db.models import Clima, LadoPista, NivelAcesso
from backend.db.repository import Repository
from backend.db.session import SessionLocal
from backend.api.routes.auth import require_auth
from backend.agents.instructions_store import (
    get_project_root,
    get_instructions_path,
    read_agent_instructions,
    write_agent_instructions,
)

api_blueprint = Blueprint("api_v1", __name__, url_prefix="/api/v1")


def _to_json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def _to_dict(model_instance):
    payload = {}
    for key in model_instance.__table__.columns.keys():
        if key == "senha":
            continue
        payload[key] = _to_json_value(getattr(model_instance, key))
    return payload


def _json_error(message: str, status_code: int = 400):
    return jsonify({"ok": False, "error": message}), status_code


def _is_admin(user) -> bool:
    nivel = user.nivel_acesso.value if hasattr(user.nivel_acesso, "value") else str(user.nivel_acesso)
    return nivel == NivelAcesso.ADMINISTRADOR.value


def _to_project_relative(path: Path) -> str:
    try:
        return str(path.relative_to(get_project_root())).replace("\\", "/")
    except ValueError:
        return str(path)


@api_blueprint.route("/agent/instructions", methods=["GET"])
@require_auth
def obter_instrucoes_agente():
    from flask import g

    if not _is_admin(g.current_user):
        return _json_error("Apenas administradores podem visualizar as instruções do agente.", 403)

    path = get_instructions_path()
    content = read_agent_instructions()
    return jsonify(
        {
            "ok": True,
            "path": _to_project_relative(path),
            "content": content,
            "exists": path.exists(),
        }
    )


@api_blueprint.route("/agent/instructions", methods=["PUT", "PATCH"])
@require_auth
def atualizar_instrucoes_agente():
    from flask import g

    if not _is_admin(g.current_user):
        return _json_error("Apenas administradores podem editar as instruções do agente.", 403)

    data = request.get_json(silent=True) or {}
    content = data.get("content")

    if not isinstance(content, str):
        return _json_error("Campo obrigatório ausente: content")

    saved_path = write_agent_instructions(content)
    return jsonify(
        {
            "ok": True,
            "path": _to_project_relative(saved_path),
            "content": content,
        }
    )


@api_blueprint.route("/usuarios", methods=["GET"])
def listar_usuarios():
    with SessionLocal() as db:
        usuarios = Repository.usuarios.listar(db)
        return jsonify([_to_dict(item) for item in usuarios])


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
        return _json_error(f"Campo obrigatório ausente: {exc.args[0]}")
    except ValueError:
        return _json_error("nivel_acesso inválido.")

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
        return jsonify(_to_dict(usuario)), 201


@api_blueprint.route("/usuarios/<int:usuario_id>", methods=["GET"])
def obter_usuario(usuario_id: int):
    with SessionLocal() as db:
        usuario = Repository.usuarios.obter_por_id(db, usuario_id)
        if not usuario:
            return _json_error("Usuário não encontrado.", 404)
        return jsonify(_to_dict(usuario))


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
            return _json_error("nivel_acesso inválido.")

    with SessionLocal() as db:
        usuario = Repository.usuarios.atualizar(db, usuario_id, **update_payload)
        if not usuario:
            return _json_error("Usuário não encontrado.", 404)
        return jsonify(_to_dict(usuario))


@api_blueprint.route("/usuarios/<int:usuario_id>", methods=["DELETE"])
def deletar_usuario(usuario_id: int):
    with SessionLocal() as db:
        ok = Repository.usuarios.deletar(db, usuario_id)
        if not ok:
            return _json_error("Usuário não encontrado.", 404)
        return jsonify({"ok": True})


@api_blueprint.route("/frentes-servico", methods=["GET"])
def listar_frentes_servico():
    with SessionLocal() as db:
        frentes = Repository.frentes_servico.listar(db)
        return jsonify([_to_dict(item) for item in frentes])


@api_blueprint.route("/frentes-servico", methods=["POST"])
def criar_frente_servico():
    data = request.get_json(silent=True) or {}
    try:
        nome = data["nome"]
    except KeyError as exc:
        return _json_error(f"Campo obrigatório ausente: {exc.args[0]}")

    with SessionLocal() as db:
        frente = Repository.frentes_servico.criar(
            db,
            nome=nome,
            encarregado_responsavel=data.get("encarregado_responsavel"),
            observacao=data.get("observacao"),
        )
        return jsonify(_to_dict(frente)), 201


@api_blueprint.route("/frentes-servico/<int:frente_id>", methods=["GET"])
def obter_frente_servico(frente_id: int):
    with SessionLocal() as db:
        frente = Repository.frentes_servico.obter_por_id(db, frente_id)
        if not frente:
            return _json_error("Frente de serviço não encontrada.", 404)
        return jsonify(_to_dict(frente))


@api_blueprint.route("/frentes-servico/<int:frente_id>", methods=["PUT", "PATCH"])
def atualizar_frente_servico(frente_id: int):
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
            return _json_error("Frente de serviço não encontrada.", 404)
        return jsonify(_to_dict(frente))


@api_blueprint.route("/frentes-servico/<int:frente_id>", methods=["DELETE"])
def deletar_frente_servico(frente_id: int):
    with SessionLocal() as db:
        ok = Repository.frentes_servico.deletar(db, frente_id)
        if not ok:
            return _json_error("Frente de serviço não encontrada.", 404)
        return jsonify({"ok": True})


def _parse_registro_payload(data: dict):
    try:
        frente_id = int(data["frente_servico_id"])
    except KeyError as exc:
        raise ValueError(f"Campo obrigatório ausente: {exc.args[0]}") from exc
    except (ValueError, TypeError):
        raise ValueError("frente_servico_id deve ser um número inteiro válido.") from None

    parsed = {
        "frente_servico_id": frente_id,
    }
    
    # Campos opcionais
    if data.get("data"):
        try:
            parsed["data"] = date.fromisoformat(data["data"])
        except Exception:
            raise ValueError("Formato inválido em data. Use YYYY-MM-DD.")
    
    if data.get("usuario_registrador_id"):
        try:
            parsed["usuario_registrador_id"] = int(data["usuario_registrador_id"])
        except (ValueError, TypeError):
            raise ValueError("usuario_registrador_id deve ser um número inteiro válido.")
    
    estaca_inicial = data.get("estaca_inicial")
    estaca_final = data.get("estaca_final")
    resultado = data.get("resultado")

    if estaca_inicial is not None:
        try:
            parsed["estaca_inicial"] = float(estaca_inicial)
        except (ValueError, TypeError):
            raise ValueError("estaca_inicial deve ser um número válido.")
    
    if estaca_final is not None:
        try:
            parsed["estaca_final"] = float(estaca_final)
        except (ValueError, TypeError):
            raise ValueError("estaca_final deve ser um número válido.")
    
    if resultado is None and parsed.get("estaca_inicial") is not None and parsed.get("estaca_final") is not None:
        parsed["resultado"] = float(parsed["estaca_final"]) - float(parsed["estaca_inicial"])
    elif resultado is not None:
        try:
            parsed["resultado"] = float(resultado)
        except (ValueError, TypeError):
            raise ValueError("resultado deve ser um número válido.")
    
    if data.get("tempo_manha"):
        try:
            parsed["tempo_manha"] = Clima(data["tempo_manha"])
        except ValueError:
            raise ValueError(f"tempo_manha inválido. Valores válidos: {', '.join([c.value for c in Clima])}")
    
    if data.get("tempo_tarde"):
        try:
            parsed["tempo_tarde"] = Clima(data["tempo_tarde"])
        except ValueError:
            raise ValueError(f"tempo_tarde inválido. Valores válidos: {', '.join([c.value for c in Clima])}")
    
    if data.get("pista"):
        try:
            parsed["pista"] = LadoPista(data["pista"])
        except ValueError:
            raise ValueError(f"pista inválido. Valores válidos: {', '.join([p.value for p in LadoPista])}")
    
    if data.get("lado_pista"):
        try:
            parsed["lado_pista"] = LadoPista(data["lado_pista"])
        except ValueError:
            raise ValueError(f"lado_pista inválido. Valores válidos: {', '.join([p.value for p in LadoPista])}")
    
    if data.get("observacao"):
        parsed["observacao"] = data["observacao"]
    
    return parsed


@api_blueprint.route("/registros", methods=["GET"])
def listar_registros():
    data_filter = request.args.get("data")
    frente_filter = request.args.get("frente_servico_id")
    usuario_filter = request.args.get("usuario_id")

    with SessionLocal() as db:
        if data_filter:
            try:
                registros = Repository.registros.listar_por_data(db, date.fromisoformat(data_filter))
            except Exception:
                return _json_error("Parâmetro data inválido. Use YYYY-MM-DD.")
        elif frente_filter:
            registros = Repository.registros.listar_por_frente(db, int(frente_filter))
        elif usuario_filter:
            registros = Repository.registros.listar_por_usuario(db, int(usuario_filter))
        else:
            registros = Repository.registros.listar(db)

        return jsonify([_to_dict(item) for item in registros])


@api_blueprint.route("/registros", methods=["POST"])
def criar_registro():
    data = request.get_json(silent=True) or {}
    try:
        parsed = _parse_registro_payload(data)
    except ValueError as exc:
        return _json_error(str(exc))

    with SessionLocal() as db:
        registro = Repository.registros.criar(db=db, **parsed)
        return jsonify(_to_dict(registro)), 201


@api_blueprint.route("/registros/<int:registro_id>", methods=["GET"])
def obter_registro(registro_id: int):
    with SessionLocal() as db:
        registro = Repository.registros.obter_por_id(db, registro_id)
        if not registro:
            return _json_error("Registro não encontrado.", 404)
        return jsonify(_to_dict(registro))


@api_blueprint.route("/registros/<int:registro_id>", methods=["PUT", "PATCH"])
def atualizar_registro(registro_id: int):
    data = request.get_json(silent=True) or {}
    payload = {
        "frente_servico_id": data.get("frente_servico_id"),
        "usuario_registrador_id": data.get("usuario_registrador_id"),
        "estaca_inicial": data.get("estaca_inicial"),
        "estaca_final": data.get("estaca_final"),
        "resultado": data.get("resultado"),
        "observacao": data.get("observacao"),
    }

    if data.get("tempo_manha"):
        try:
            payload["tempo_manha"] = Clima(data["tempo_manha"])
        except ValueError:
            return _json_error(f"tempo_manha inválido. Valores válidos: {', '.join([c.value for c in Clima])}")
    
    if data.get("tempo_tarde"):
        try:
            payload["tempo_tarde"] = Clima(data["tempo_tarde"])
        except ValueError:
            return _json_error(f"tempo_tarde inválido. Valores válidos: {', '.join([c.value for c in Clima])}")
    
    if data.get("pista"):
        try:
            payload["pista"] = LadoPista(data["pista"])
        except ValueError:
            return _json_error(f"pista inválido. Valores válidos: {', '.join([p.value for p in LadoPista])}")
    
    if data.get("lado_pista"):
        try:
            payload["lado_pista"] = LadoPista(data["lado_pista"])
        except ValueError:
            return _json_error(f"lado_pista inválido. Valores válidos: {', '.join([p.value for p in LadoPista])}")

    if data.get("data"):
        try:
            payload["data"] = date.fromisoformat(data["data"])
        except Exception:
            return _json_error("Campo data inválido. Use YYYY-MM-DD.")

    # Calcular resultado a partir de estacas se necessário
    estaca_inicial = payload.get("estaca_inicial")
    estaca_final = payload.get("estaca_final")
    if estaca_inicial is not None and estaca_final is not None and payload.get("resultado") is None:
        payload["resultado"] = float(estaca_final) - float(estaca_inicial)

    with SessionLocal() as db:
        registro = Repository.registros.atualizar(db, registro_id, **payload)
        if not registro:
            return _json_error("Registro não encontrado.", 404)
        return jsonify(_to_dict(registro))


@api_blueprint.route("/registros/<int:registro_id>", methods=["DELETE"])
def deletar_registro(registro_id: int):
    with SessionLocal() as db:
        ok = Repository.registros.deletar(db, registro_id)
        if not ok:
            return _json_error("Registro não encontrado.", 404)
        return jsonify({"ok": True})
