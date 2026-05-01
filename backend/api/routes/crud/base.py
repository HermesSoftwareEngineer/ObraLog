from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
import json
import os
import unicodedata
from uuid import UUID

from flask import Blueprint, jsonify

from backend.agents.instructions_store import get_project_root
from backend.db.models import (
    Clima,
    LadoPista,
    NivelAcesso,
    RegistroStatus,
    MensagemCampo,
)


api_blueprint = Blueprint("api_v1", __name__, url_prefix="/api/v1")

UPLOAD_DIR = Path(os.environ.get("REGISTRO_IMAGENS_DIR", str(Path("backend") / "uploads" / "registros")))
MAX_IMAGENS_POR_REGISTRO = 30
ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}


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
    if getattr(model_instance, "__tablename__", None) == "registros":
        payload.setdefault("pista", payload.get("lado_pista"))
        # Construir o hybrid schema localizacao no payload
        localizacao = {"tipo": "ESTACA"}
        if payload.get("metadata_json") and isinstance(payload["metadata_json"], dict):
            localizacao["tipo"] = payload["metadata_json"].get("tipo", "ESTACA")
        localizacao["detalhe_texto"] = payload.get("estaca")
        localizacao["valor_inicial"] = payload.get("estaca_inicial")
        localizacao["valor_final"] = payload.get("estaca_final")
        payload["localizacao"] = localizacao
    return payload


def _json_error(message: str, status_code: int = 400):
    return jsonify({"ok": False, "error": message}), status_code


def _to_imagem_dict(item):
    return {
        "id": item.id,
        "registro_id": item.registro_id,
        "storage_path": item.storage_path,
        "external_url": item.external_url,
        "mime_type": item.mime_type,
        "file_size": item.file_size,
        "origem": item.origem,
        "created_at": _to_json_value(item.created_at),
    }


def _guess_extension(filename: str, mime_type: str | None) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}:
        return suffix
    by_mime = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/heic": ".heic",
        "image/heif": ".heif",
    }
    return by_mime.get(mime_type or "", ".bin")


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.strip().lower().split())


def _parse_lado_pista(value: str, field_name: str) -> LadoPista:
    normalized = _normalize_text(value)
    aliases = {
        "direito": LadoPista.DIREITO,
        "lado direito": LadoPista.DIREITO,
        "direita": LadoPista.DIREITO,
        "lado direita": LadoPista.DIREITO,
        "dir": LadoPista.DIREITO,
        "esquerdo": LadoPista.ESQUERDO,
        "lado esquerdo": LadoPista.ESQUERDO,
        "esquerda": LadoPista.ESQUERDO,
        "lado esquerda": LadoPista.ESQUERDO,
        "esq": LadoPista.ESQUERDO,
    }
    parsed = aliases.get(normalized)
    if parsed is None:
        raise ValueError(f"{field_name} invalido. Valores validos: direito, esquerdo")
    return parsed


def _parse_clima(value: str, field_name: str) -> Clima:
    normalized = _normalize_text(value)
    aliases = {
        "limpo": Clima.LIMPO,
        "sol": Clima.LIMPO,
        "ensolarado": Clima.LIMPO,
        "nublado": Clima.NUBLADO,
        "chuva": Clima.NUBLADO,
        "chuvoso": Clima.NUBLADO,
        "impraticavel": Clima.IMPRATICAVEL,
        "impraticavel total": Clima.IMPRATICAVEL,
    }
    parsed = aliases.get(normalized)
    if parsed is None:
        raise ValueError(f"{field_name} invalido. Valores validos: limpo, nublado, impraticavel")
    return parsed


def _is_admin(user) -> bool:
    nivel = user.nivel_acesso.value if hasattr(user.nivel_acesso, "value") else str(user.nivel_acesso)
    return nivel == NivelAcesso.ADMINISTRADOR.value


def _to_project_relative(path: Path) -> str:
    try:
        return str(path.relative_to(get_project_root())).replace("\\", "/")
    except ValueError:
        return str(path)


def _resolve_upload_filename(filename: str) -> str | None:
    normalized = (filename or "").replace("\\", "/").strip("/")
    if not normalized:
        return None
    return Path(normalized).name


def _parse_uuid(value: str | None, field_name: str) -> UUID:
    if not value:
        raise ValueError(f"Campo obrigatorio ausente: {field_name}")
    try:
        return UUID(str(value))
    except Exception as exc:
        raise ValueError(f"{field_name} invalido. Use UUID valido.") from exc


def _parse_optional_uuid(value: str | None, field_name: str) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except Exception as exc:
        raise ValueError(f"{field_name} invalido. Use UUID valido.") from exc


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _serialize_mensagem_campo(item: MensagemCampo) -> dict:
    payload = _to_dict(item)
    if item.payload_json:
        try:
            payload["payload_json"] = json.loads(item.payload_json)
        except Exception:
            payload["payload_json"] = item.payload_json
    return payload


def _parse_processamento_status(value: str):
    raw = _normalize_text(value)
    valid = {"pendente", "processada", "erro"}
    if raw not in valid:
        raise ValueError("status invalido. Valores validos: pendente, processada, erro")
    return raw


def _parse_registro_status(value: str, field_name: str = "status") -> RegistroStatus:
    raw = _normalize_text(value)
    aliases = {
        "pendente": RegistroStatus.PENDENTE,
        "consolidado": RegistroStatus.CONSOLIDADO,
        "revisado": RegistroStatus.REVISADO,
        "ativo": RegistroStatus.ATIVO,
        "descartado": RegistroStatus.DESCARTADO,
    }
    parsed = aliases.get(raw)
    if not parsed:
        raise ValueError(f"{field_name} invalido. Valores validos: pendente, consolidado, revisado, ativo, descartado")
    return parsed
