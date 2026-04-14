from datetime import date
from pathlib import Path
from uuid import uuid4

from flask import request, send_from_directory
from werkzeug.utils import secure_filename

from backend.db.repository import Repository
from backend.db.session import SessionLocal

from .base import (
    ALLOWED_IMAGE_MIME_TYPES,
    MAX_IMAGENS_POR_REGISTRO,
    UPLOAD_DIR,
    api_blueprint,
    _guess_extension,
    _json_error,
    _parse_clima,
    _parse_lado_pista,
    _parse_registro_status,
    _resolve_upload_filename,
    _to_dict,
    _to_imagem_dict,
)


def _parse_registro_payload(data: dict):
    parsed = {}

    if data.get("status") is not None:
        parsed["status"] = _parse_registro_status(str(data.get("status")), "status")

    if data.get("frente_servico_id") not in (None, ""):
        try:
            parsed["frente_servico_id"] = int(data["frente_servico_id"])
        except (ValueError, TypeError):
            raise ValueError("frente_servico_id deve ser um numero inteiro valido.") from None

    if data.get("data") not in (None, ""):
        try:
            parsed["data"] = date.fromisoformat(data["data"])
        except Exception:
            raise ValueError("Formato invalido em data. Use YYYY-MM-DD.")

    if data.get("usuario_registrador_id") not in (None, ""):
        try:
            parsed["usuario_registrador_id"] = int(data["usuario_registrador_id"])
        except (ValueError, TypeError):
            raise ValueError("usuario_registrador_id deve ser um numero inteiro valido.")

    if data.get("estaca_inicial") not in (None, ""):
        try:
            parsed["estaca_inicial"] = float(data.get("estaca_inicial"))
        except (ValueError, TypeError):
            raise ValueError("estaca_inicial deve ser um numero valido.")

    if data.get("estaca_final") not in (None, ""):
        try:
            parsed["estaca_final"] = float(data.get("estaca_final"))
        except (ValueError, TypeError):
            raise ValueError("estaca_final deve ser um numero valido.")

    if data.get("resultado") not in (None, ""):
        try:
            parsed["resultado"] = float(data.get("resultado"))
        except (ValueError, TypeError):
            raise ValueError("resultado deve ser um numero valido.")

    if parsed.get("resultado") is None and parsed.get("estaca_inicial") is not None and parsed.get("estaca_final") is not None:
        parsed["resultado"] = float(parsed["estaca_final"]) - float(parsed["estaca_inicial"])

    if data.get("tempo_manha") not in (None, ""):
        try:
            parsed["tempo_manha"] = _parse_clima(data["tempo_manha"], "tempo_manha")
        except ValueError as exc:
            raise ValueError(str(exc))

    if data.get("tempo_tarde") not in (None, ""):
        try:
            parsed["tempo_tarde"] = _parse_clima(data["tempo_tarde"], "tempo_tarde")
        except ValueError as exc:
            raise ValueError(str(exc))

    if data.get("lado_pista"):
        parsed["lado_pista"] = _parse_lado_pista(data["lado_pista"], "lado_pista")
    elif data.get("pista"):
        parsed["lado_pista"] = _parse_lado_pista(data["pista"], "pista")

    if "observacao" in data:
        observacao = str(data.get("observacao") or "").strip()
        parsed["observacao"] = observacao or None
    else:
        parsed["observacao"] = None

    if "raw_text" in data:
        raw_text = str(data.get("raw_text") or "").strip()
        parsed["raw_text"] = raw_text or None

    if "source_message_id" in data:
        parsed["source_message_id"] = data.get("source_message_id")

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
                return _json_error("Parametro data invalido. Use YYYY-MM-DD.")
        elif frente_filter:
            registros = Repository.registros.listar_por_frente(db, int(frente_filter))
        elif usuario_filter:
            registros = Repository.registros.listar_por_usuario(db, int(usuario_filter))
        else:
            registros = Repository.registros.listar(db)

        return [_to_dict(item) for item in registros]


@api_blueprint.route("/registros", methods=["POST"])
def criar_registro():
    data = request.get_json(silent=True) or {}
    try:
        parsed = _parse_registro_payload(data)
    except ValueError as exc:
        return _json_error(str(exc))

    with SessionLocal() as db:
        try:
            registro = Repository.registros.criar(db=db, **parsed)
        except ValueError as exc:
            return _json_error(str(exc), 422)
        return _to_dict(registro), 201


@api_blueprint.route("/registros/<int:registro_id>", methods=["GET"])
def obter_registro(registro_id: int):
    with SessionLocal() as db:
        registro = Repository.registros.obter_por_id(db, registro_id)
        if not registro:
            return _json_error("Registro nao encontrado.", 404)
        return _to_dict(registro)


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
        "raw_text": data.get("raw_text"),
        "source_message_id": data.get("source_message_id"),
    }

    if data.get("tempo_manha"):
        try:
            payload["tempo_manha"] = _parse_clima(data["tempo_manha"], "tempo_manha")
        except ValueError as exc:
            return _json_error(str(exc))

    if data.get("tempo_tarde"):
        try:
            payload["tempo_tarde"] = _parse_clima(data["tempo_tarde"], "tempo_tarde")
        except ValueError as exc:
            return _json_error(str(exc))

    if data.get("lado_pista"):
        try:
            payload["lado_pista"] = _parse_lado_pista(data["lado_pista"], "lado_pista")
        except ValueError as exc:
            return _json_error(str(exc))
    elif data.get("pista"):
        try:
            payload["lado_pista"] = _parse_lado_pista(data["pista"], "pista")
        except ValueError as exc:
            return _json_error(str(exc))

    if data.get("data"):
        try:
            payload["data"] = date.fromisoformat(data["data"])
        except Exception:
            return _json_error("Campo data invalido. Use YYYY-MM-DD.")

    estaca_inicial = payload.get("estaca_inicial")
    estaca_final = payload.get("estaca_final")
    if estaca_inicial is not None and estaca_final is not None and payload.get("resultado") is None:
        payload["resultado"] = float(estaca_final) - float(estaca_inicial)

    with SessionLocal() as db:
        try:
            registro = Repository.registros.atualizar(db, registro_id, **payload)
        except ValueError as exc:
            return _json_error(str(exc), 422)
        if not registro:
            return _json_error("Registro nao encontrado.", 404)
        return _to_dict(registro)


@api_blueprint.route("/registros/<int:registro_id>/status", methods=["PATCH"])
def atualizar_status_registro(registro_id: int):
    data = request.get_json(silent=True) or {}
    status_value = data.get("status")
    if status_value in (None, ""):
        return _json_error("Campo obrigatorio ausente: status", 422)

    try:
        parsed_status = _parse_registro_status(str(status_value), "status")
    except ValueError as exc:
        return _json_error(str(exc), 422)

    with SessionLocal() as db:
        try:
            registro = Repository.registros.atualizar_status(db, registro_id, parsed_status)
        except ValueError as exc:
            return _json_error(str(exc), 422)

        if not registro:
            return _json_error("Registro nao encontrado.", 404)
        return {"ok": True, "registro": _to_dict(registro)}


@api_blueprint.route("/registros/<int:registro_id>", methods=["DELETE"])
def deletar_registro(registro_id: int):
    with SessionLocal() as db:
        ok = Repository.registros.deletar(db, registro_id)
        if not ok:
            return _json_error("Registro nao encontrado.", 404)
        return {"ok": True}


@api_blueprint.route("/registros/<int:registro_id>/imagens", methods=["GET"])
def listar_imagens_registro(registro_id: int):
    with SessionLocal() as db:
        registro = Repository.registros.obter_por_id(db, registro_id)
        if not registro:
            return _json_error("Registro nao encontrado.", 404)
        imagens = Repository.registro_imagens.listar_por_registro(db, registro_id)
        return [_to_imagem_dict(item) for item in imagens]


@api_blueprint.route("/registros/<int:registro_id>/imagens", methods=["POST"])
def upload_imagem_registro(registro_id: int):
    uploaded = request.files.get("imagem")
    if not uploaded:
        return _json_error("Arquivo obrigatorio ausente: imagem")

    mime_type = (uploaded.mimetype or "").lower().strip()
    if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
        return _json_error("Tipo de imagem nao suportado. Use JPEG, PNG, WEBP, HEIC ou HEIF.")

    with SessionLocal() as db:
        registro = Repository.registros.obter_por_id(db, registro_id)
        if not registro:
            return _json_error("Registro nao encontrado.", 404)

        total = Repository.registro_imagens.contar_por_registro(db, registro_id)
        if total >= MAX_IMAGENS_POR_REGISTRO:
            return _json_error("Limite de 30 imagens por registro atingido.", 409)

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        original_name = secure_filename(uploaded.filename or "imagem")
        extension = _guess_extension(original_name, mime_type)
        file_name = f"registro_{registro_id}_{uuid4().hex}{extension}"
        full_path = UPLOAD_DIR / file_name
        uploaded.save(full_path)

        file_size = full_path.stat().st_size if full_path.exists() else None
        relative_path = str(full_path).replace("\\", "/")
        imagem = Repository.registro_imagens.criar(
            db,
            registro_id=registro_id,
            storage_path=relative_path,
            mime_type=mime_type,
            file_size=file_size,
            origem="api",
        )
        return _to_imagem_dict(imagem), 201


@api_blueprint.route("/registros/<int:registro_id>/imagens/<int:imagem_id>", methods=["DELETE"])
def deletar_imagem_registro(registro_id: int, imagem_id: int):
    with SessionLocal() as db:
        registro = Repository.registros.obter_por_id(db, registro_id)
        if not registro:
            return _json_error("Registro nao encontrado.", 404)

        imagem = Repository.registro_imagens.obter_por_id(db, imagem_id)
        if not imagem or imagem.registro_id != registro_id:
            return _json_error("Imagem nao encontrada para este registro.", 404)

        storage_path = imagem.storage_path
        ok = Repository.registro_imagens.deletar(db, imagem_id)
        if not ok:
            return _json_error("Imagem nao encontrada.", 404)

        if storage_path:
            try:
                saved_file = Path(storage_path)
                if saved_file.exists():
                    saved_file.unlink()
            except OSError:
                pass

        return {"ok": True}


@api_blueprint.route("/backend/uploads/registros/<path:filename>", methods=["GET"])
def baixar_imagem_registro(filename: str):
    resolved_name = _resolve_upload_filename(filename)
    if not resolved_name:
        return _json_error("Nome de arquivo invalido.", 400)

    target_path = UPLOAD_DIR / resolved_name
    if not target_path.exists() or not target_path.is_file():
        return _json_error("Imagem nao encontrada.", 404)

    return send_from_directory(UPLOAD_DIR.resolve(), resolved_name)
