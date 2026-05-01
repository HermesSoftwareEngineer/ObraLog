from __future__ import annotations

from datetime import date
import unicodedata
from uuid import UUID
from typing import Any

from .errors import GatewayValidationError


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.strip().lower().split())


def to_optional_str(value: object) -> str | None:
    if value is None:
        return None
    as_text = str(value).strip()
    return as_text or None


def parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(str(value))
    except Exception as exc:
        raise GatewayValidationError(f"{field_name} must be a valid UUID.") from exc


def parse_optional_uuid(value: str | None, field_name: str) -> UUID | None:
    if value in (None, ""):
        return None
    return parse_uuid(value, field_name)


def parse_iso_date(value: str, field_name: str) -> date:
    raw = str(value or "").strip()
    if not raw:
        raise GatewayValidationError(f"{field_name} is required.")

    try:
        return date.fromisoformat(raw)
    except Exception:
        pass

    try:
        day, month, year = raw.split("/")
        return date(year=int(year), month=int(month), day=int(day))
    except Exception as exc:
        raise GatewayValidationError(
            f"{field_name} must use YYYY-MM-DD or DD/MM/YYYY format."
        ) from exc


def clamp_limit(limit: int, *, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(limit)
    except Exception:
        return default
    return max(min_value, min(parsed, max_value))


TECHNICAL_KEY_BLOCKLIST = {
    "id",
    "read_by",
    "reported_by",
    "resolved_by",
    "actor_user_id",
    "owner_user_id",
    "request_id",
    "message_id",
    "poll_id",
    "telegram_message_id",
}


def is_technical_key(key: str) -> bool:
    normalized = str(key).strip().lower()
    if normalized in TECHNICAL_KEY_BLOCKLIST:
        return True
    return normalized.endswith("_id")


def strip_technical_keys(payload: Any) -> Any:
    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            if is_technical_key(str(key)):
                continue
            cleaned[key] = strip_technical_keys(value)
        return cleaned
    if isinstance(payload, list):
        return [strip_technical_keys(item) for item in payload]
    return payload


def has_technical_keys(payload: Any) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if is_technical_key(str(key)):
                return True
            if has_technical_keys(value):
                return True
        return False
    if isinstance(payload, list):
        return any(has_technical_keys(item) for item in payload)
    return False


def summarize_registro_item(item: dict[str, Any], frente_nome: str | None = None) -> dict[str, Any]:
    return {
        "data": item.get("data"),
        "obra_id": item.get("obra_id"),
        "frente_servico_nome": frente_nome,
        "estaca_inicial": item.get("estaca_inicial"),
        "estaca_final": item.get("estaca_final"),
        "resultado": item.get("resultado"),
        "tempo_manha": item.get("tempo_manha"),
        "tempo_tarde": item.get("tempo_tarde"),
        "observacao": item.get("observacao"),
        "lado_pista": item.get("lado_pista") or item.get("pista"),
        "imagens_total": item.get("imagens_total"),
        "registrador_nome": item.get("registrador_nome"),
    }


def map_consultar_diario_obra_output(
    raw: dict[str, Any],
    *,
    frentes_by_id: dict[int, str] | None = None,
    requested_frente_nome: str | None = None,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"ok": False, "message": "Resposta invalida da consulta de diario."}

    if not raw.get("ok"):
        return strip_technical_keys(raw)

    diario = raw.get("diario") if isinstance(raw.get("diario"), dict) else {}
    registros = diario.get("registros") if isinstance(diario.get("registros"), list) else []
    frentes_by_id = frentes_by_id or {}

    registros_out: list[dict[str, Any]] = []
    frentes_no_dia: set[str] = set()
    for registro in registros:
        if not isinstance(registro, dict):
            continue
        frente_id = registro.get("frente_servico_id")
        frente_nome = requested_frente_nome
        if frente_nome is None and isinstance(frente_id, int):
            frente_nome = frentes_by_id.get(frente_id)
        if frente_nome:
            frentes_no_dia.add(frente_nome)
        registros_out.append(summarize_registro_item(registro, frente_nome=frente_nome))

    frente_nome_final = requested_frente_nome
    if not frente_nome_final and len(frentes_no_dia) == 1:
        frente_nome_final = next(iter(frentes_no_dia))

    payload = {
        "ok": True,
        "consulta": {
            "data": diario.get("data"),
            "frente_servico_nome": frente_nome_final,
            "clima": diario.get("resumo_clima"),
            "totais": {
                "total_registros": diario.get("total_registros", 0),
                "total_resultado": diario.get("total_resultado", 0.0),
                "dias_impraticaveis": diario.get("dias_impraticaveis", False),
            },
            "registros": registros_out,
        },
    }
    return strip_technical_keys(payload)


def map_consultar_producao_periodo_output(
    raw: dict[str, Any],
    *,
    frentes_by_id: dict[int, str] | None = None,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"ok": False, "message": "Resposta invalida da consulta por periodo."}

    if not raw.get("ok"):
        return strip_technical_keys(raw)

    relatorio = raw.get("relatorio") if isinstance(raw.get("relatorio"), dict) else {}
    dias_raw = relatorio.get("dias") if isinstance(relatorio.get("dias"), list) else []
    frentes_by_id = frentes_by_id or {}

    resumo_por_frente: dict[str, dict[str, Any]] = {}
    dias: list[dict[str, Any]] = []

    for dia in dias_raw:
        if not isinstance(dia, dict):
            continue
        registros = dia.get("registros") if isinstance(dia.get("registros"), list) else []
        frentes_do_dia: set[str] = set()
        for registro in registros:
            if not isinstance(registro, dict):
                continue
            frente_nome = None
            frente_id = registro.get("frente_servico_id")
            if isinstance(frente_id, int):
                frente_nome = frentes_by_id.get(frente_id)
            if not frente_nome:
                continue
            frentes_do_dia.add(frente_nome)
            bucket = resumo_por_frente.setdefault(
                frente_nome,
                {
                    "frente_servico_nome": frente_nome,
                    "total_resultado": 0.0,
                    "total_registros": 0,
                    "dias_com_registro": set(),
                },
            )
            bucket["total_resultado"] += float(registro.get("resultado") or 0.0)
            bucket["total_registros"] += 1
            if dia.get("data"):
                bucket["dias_com_registro"].add(str(dia.get("data")))

        dias.append(
            {
                "data": dia.get("data"),
                "clima": dia.get("resumo_clima"),
                "total_registros": dia.get("total_registros", 0),
                "total_resultado": dia.get("total_resultado", 0.0),
                "dias_impraticaveis": dia.get("dias_impraticaveis", False),
                "frentes_servico": sorted(frentes_do_dia),
            }
        )

    resumo_por_frente_out = []
    for item in resumo_por_frente.values():
        resumo_por_frente_out.append(
            {
                "frente_servico_nome": item["frente_servico_nome"],
                "total_resultado": round(float(item["total_resultado"]), 2),
                "total_registros": int(item["total_registros"]),
                "dias_com_registro": len(item["dias_com_registro"]),
            }
        )
    resumo_por_frente_out.sort(key=lambda it: (-float(it["total_resultado"]), str(it["frente_servico_nome"])))

    payload = {
        "ok": True,
        "consulta": {
            "resumo_periodo": {
                "data_inicio": relatorio.get("data_inicio"),
                "data_fim": relatorio.get("data_fim"),
                "total_resultado_periodo": relatorio.get("total_resultado_periodo", 0.0),
                "total_dias": relatorio.get("total_dias", 0),
                "total_dias_impraticaveis": relatorio.get("total_dias_impraticaveis", 0),
                "media_diaria": relatorio.get("media_diaria", 0.0),
            },
            "resumo_por_frente": resumo_por_frente_out,
            "dias": dias,
        },
    }
    return strip_technical_keys(payload)


def map_alerta_to_business(alerta: dict[str, Any]) -> dict[str, Any]:
    """Converte um dict tecnico de alerta para chaves de negocio em PT-BR."""
    return {
        "codigo": alerta.get("code") or alerta.get("codigo"),
        "tipo": alerta.get("type") or alerta.get("tipo"),
        "obra_id": alerta.get("obra_id"),
        "severidade": alerta.get("severity") or alerta.get("severidade"),
        "status": alerta.get("status"),
        "titulo": alerta.get("title") or alerta.get("titulo"),
        "descricao": alerta.get("description") or alerta.get("descricao"),
        "local": alerta.get("location_detail") or alerta.get("local"),
        "equipamento": alerta.get("equipment_name") or alerta.get("equipamento"),
        "datas": {
            "criado_em": alerta.get("created_at"),
            "atualizado_em": alerta.get("updated_at"),
            "resolvido_em": alerta.get("resolved_at"),
            "lido_em": alerta.get("read_at"),
        },
    }


def map_consultar_alertas_operacionais_output(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"ok": False, "message": "Resposta invalida da consulta de alertas."}

    if not raw.get("ok"):
        return strip_technical_keys(raw)

    alertas_raw = raw.get("alertas") if isinstance(raw.get("alertas"), list) else []
    alertas: list[dict[str, Any]] = []
    for alerta in alertas_raw:
        if not isinstance(alerta, dict):
            continue
        alertas.append(map_alerta_to_business(alerta))

    payload = {
        "ok": True,
        "consulta": {
            "total": int(raw.get("total") or len(alertas)),
            "alertas": alertas,
            "message": raw.get("message"),
            "next_steps": raw.get("next_steps", []),
        },
    }
    return strip_technical_keys(payload)


