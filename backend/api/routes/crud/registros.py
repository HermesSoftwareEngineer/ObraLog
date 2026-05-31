from datetime import date
from pathlib import Path
from uuid import uuid4

from flask import request, send_from_directory, g
from werkzeug.utils import secure_filename

from backend.db.repository import Repository, RegistroSchemaRepository
from backend.db.session import SessionLocal
from backend.api.routes.auth import require_auth

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


def _enrich_with_schema(payload: dict, registro, db, tenant_id: int) -> None:
    """Adiciona schema e campos_extras_valores ao payload de um registro."""
    schema = None
    if registro.registro_schema_id:
        schema = RegistroSchemaRepository.obter_por_id(db, registro.registro_schema_id, tenant_id)
    elif registro.frente_servico_id:
        schema = RegistroSchemaRepository.obter_para_frente(db, registro.frente_servico_id, tenant_id)

    if not schema:
        payload["schema"] = None
        payload["campos_extras_valores"] = {}
        return

    tipo_slug = schema.tipo_obra_ref.slug if schema.tipo_obra_ref else schema.tipo_obra
    tipo_nome = schema.tipo_obra_ref.nome if schema.tipo_obra_ref else schema.tipo_obra
    payload["schema"] = {
        "id": schema.id,
        "tipo_obra": tipo_slug,
        "tipo_obra_id": schema.tipo_obra_id,
        "tipo_obra_nome": tipo_nome,
        "campos_ativos": schema.campos_ativos or {},
        "campos_extras": schema.campos_extras or [],
    }

    extras_vals: dict = {}
    meta = registro.metadata_json or {}
    if isinstance(meta, dict) and schema.campos_extras:
        for campo in schema.campos_extras:
            key = campo.get("key")
            if key and key in meta:
                extras_vals[key] = meta[key]
    payload["campos_extras_valores"] = extras_vals


def _parse_registro_payload(data: dict):
    parsed = {}

    if data.get("obra_id") not in (None, ""):
        try:
            parsed["obra_id"] = int(data["obra_id"])
        except (ValueError, TypeError):
            raise ValueError("obra_id deve ser um numero inteiro valido.") from None

    if data.get("registro_schema_id") not in (None, ""):
        try:
            parsed["registro_schema_id"] = int(data["registro_schema_id"])
        except (ValueError, TypeError):
            raise ValueError("registro_schema_id deve ser um numero inteiro valido.") from None

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

    if data.get("localizacao") is not None:
        loc = data["localizacao"]
        if loc.get("detalhe_texto"):
            parsed["localizacao"] = str(loc["detalhe_texto"])
        if loc.get("valor_inicial") is not None:
            parsed["estaca_inicial"] = float(loc["valor_inicial"])
        if loc.get("valor_final") is not None:
            parsed["estaca_final"] = float(loc["valor_final"])
        parsed["metadata_json"] = {"tipo": loc.get("tipo")}

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

    # Aceita localizacao diretamente quando não vem via objeto localizacao
    if "localizacao" in data and "localizacao" not in parsed:
        estaca_val = str(data.get("localizacao") or "").strip()
        parsed["localizacao"] = estaca_val or None

    # Campos extras do schema: mescla no metadata_json preservando tipo de localização
    if data.get("campos_extras_valores") and isinstance(data["campos_extras_valores"], dict):
        current_meta = parsed.get("metadata_json") or {}
        parsed["metadata_json"] = {**current_meta, **data["campos_extras_valores"]}

    return parsed


@api_blueprint.route("/registros", methods=["GET"])
@require_auth
def listar_registros():
    data_filter = request.args.get("data")
    obra_filter = request.args.get("obra_id")
    frente_filter = request.args.get("frente_servico_id")
    usuario_filter = request.args.get("usuario_id")
    status_filter = request.args.get("status")
    tenant_id = getattr(g, "tenant_id", None)

    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(200, max(1, int(request.args.get("per_page", 50))))
    except (ValueError, TypeError):
        return _json_error("Parametros page e per_page devem ser inteiros.")

    parsed_status = None
    if status_filter:
        try:
            parsed_status = _parse_registro_status(status_filter, "status")
        except ValueError as exc:
            return _json_error(str(exc))

    with SessionLocal() as db:
        from backend.db.models import Registro, RegistroStatus as RS
        q = db.query(Registro).filter(Registro.tenant_id == tenant_id)

        if data_filter:
            try:
                q = q.filter(Registro.data == date.fromisoformat(data_filter))
            except Exception:
                return _json_error("Parametro data invalido. Use YYYY-MM-DD.")
        if obra_filter:
            q = q.filter(Registro.obra_id == int(obra_filter))
        if frente_filter:
            q = q.filter(Registro.frente_servico_id == int(frente_filter))
        if usuario_filter:
            q = q.filter(Registro.usuario_registrador_id == int(usuario_filter))
        if parsed_status is not None:
            q = q.filter(Registro.status == parsed_status)

        total = q.count()
        registros = (
            q.order_by(Registro.data.desc(), Registro.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        return {
            "items": [_to_dict(item) for item in registros],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
        }


@api_blueprint.route("/registros", methods=["POST"])
@require_auth
def criar_registro():
    data = request.get_json(silent=True) or {}
    tenant_id = getattr(g, "tenant_id", None)
    try:
        parsed = _parse_registro_payload(data)
        parsed["tenant_id"] = tenant_id
    except ValueError as exc:
        return _json_error(str(exc))

    if parsed.get("obra_id") is None:
        return _json_error("Campo obrigatorio ausente: obra_id", 422)

    with SessionLocal() as db:
        try:
            registro = Repository.registros.criar(db=db, **parsed)
        except ValueError as exc:
            return _json_error(str(exc), 422)
        return _to_dict(registro), 201


@api_blueprint.route("/registros/<int:registro_id>", methods=["GET"])
@require_auth
def obter_registro(registro_id: int):
    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        registro = Repository.registros.obter_por_id(db, registro_id, tenant_id=tenant_id)
        if not registro:
            return _json_error("Registro nao encontrado.", 404)
        payload = _to_dict(registro)
        _enrich_with_schema(payload, registro, db, tenant_id)
        return payload


@api_blueprint.route("/registros/<int:registro_id>", methods=["PUT", "PATCH"])
@require_auth
def atualizar_registro(registro_id: int):
    tenant_id = getattr(g, "tenant_id", None)
    data = request.get_json(silent=True) or {}

    obra_id = data.get("obra_id")
    if obra_id not in (None, ""):
        try:
            obra_id = int(obra_id)
        except (ValueError, TypeError):
            return _json_error("obra_id deve ser um numero inteiro valido.")

    payload = {
        "obra_id": obra_id,
        "frente_servico_id": data.get("frente_servico_id"),
        "usuario_registrador_id": data.get("usuario_registrador_id"),
        "observacao": data.get("observacao"),
        "raw_text": data.get("raw_text"),
        "source_message_id": data.get("source_message_id"),
    }

    if data.get("localizacao") is not None and isinstance(data["localizacao"], dict):
        loc = data["localizacao"]
        if "detalhe_texto" in loc:
            payload["localizacao"] = str(loc["detalhe_texto"]) if loc["detalhe_texto"] else None
        if "valor_inicial" in loc:
            payload["estaca_inicial"] = float(loc["valor_inicial"]) if loc["valor_inicial"] is not None else None
        if "valor_final" in loc:
            payload["estaca_final"] = float(loc["valor_final"]) if loc["valor_final"] is not None else None
        if "tipo" in loc:
            payload["metadata_json"] = {"tipo": loc["tipo"]}
    else:
        if "localizacao" in data and not isinstance(data["localizacao"], dict):
            estaca_val = str(data.get("localizacao") or "").strip()
            payload["localizacao"] = estaca_val or None
        if "estaca_inicial" in data:
            payload["estaca_inicial"] = data.get("estaca_inicial")
        if "estaca_final" in data:
            payload["estaca_final"] = data.get("estaca_final")
            
    if "resultado" in data:
        payload["resultado"] = data.get("resultado")

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

    if data.get("campos_extras_valores") and isinstance(data["campos_extras_valores"], dict):
        current_meta = payload.get("metadata_json") or {}
        payload["metadata_json"] = {**current_meta, **data["campos_extras_valores"]}

    with SessionLocal() as db:
        try:
            registro = Repository.registros.atualizar(db, registro_id, tenant_id=tenant_id, **payload)
        except ValueError as exc:
            return _json_error(str(exc), 422)
        if not registro:
            return _json_error("Registro nao encontrado.", 404)
        payload_resp = _to_dict(registro)
        _enrich_with_schema(payload_resp, registro, db, tenant_id)
        return payload_resp


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

        original_name = secure_filename(uploaded.filename or "imagem")
        extension = _guess_extension(original_name, mime_type)
        img_bytes = uploaded.read()
        file_size = len(img_bytes)

        from backend.utils.storage import upload_imagem_registro as _upload_storage
        try:
            storage_path = _upload_storage(
                tenant_id=registro.tenant_id,
                registro_id=registro_id,
                img_bytes=img_bytes,
                mime_type=mime_type,
                suffix=extension,
            )
        except Exception as exc:
            return _json_error(f"Falha ao armazenar imagem: {exc}", 502)

        imagem = Repository.registro_imagens.criar(
            db,
            registro_id=registro_id,
            storage_path=storage_path,
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
