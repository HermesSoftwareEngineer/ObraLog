from __future__ import annotations

from datetime import date
from decimal import Decimal

from flask import Blueprint, jsonify, make_response, request, g

from backend.api.routes.auth import require_auth
from backend.api.schemas_diario import (
    DiarioDoDiaOut,
    DiarioRelatorioOut,
    FrenteServicoSummary,
    ImagemOut,
    RegistroOut,
)
from backend.db.diario_repository import agrupar_por_data, get_diario_do_dia, get_registros_por_periodo
from backend.db.repository import Repository
from backend.db.session import SessionLocal


router = Blueprint("diario_v1", __name__, url_prefix="/api/v1/diario")


def _json_error(message: str, status_code: int = 400):
    return jsonify({"ok": False, "error": message}), status_code


def _to_float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _parse_date(value: str | None, field_name: str) -> date:
    if not value:
        raise ValueError(f"Parâmetro obrigatório ausente: {field_name}")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Parâmetro inválido: {field_name}. Use YYYY-MM-DD.")


def _parse_optional_int(value: str | None, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Parâmetro inválido: {field_name}. Use número inteiro.")


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _build_resumo_clima(registros: list) -> str:
    manha = sorted({(r.tempo_manha.value if hasattr(r.tempo_manha, "value") else str(r.tempo_manha)) for r in registros})
    tarde = sorted({(r.tempo_tarde.value if hasattr(r.tempo_tarde, "value") else str(r.tempo_tarde)) for r in registros})
    return f"Manhã: {', '.join(manha)} | Tarde: {', '.join(tarde)}"


def _is_dia_impraticavel(registros: list) -> bool:
    if not registros:
        return False
    return all(
        (r.tempo_manha.value if hasattr(r.tempo_manha, "value") else str(r.tempo_manha)) == "impraticavel"
        and (r.tempo_tarde.value if hasattr(r.tempo_tarde, "value") else str(r.tempo_tarde)) == "impraticavel"
        for r in registros
    )


def _frente_summary_from_registros(registros: list) -> FrenteServicoSummary | None:
    if not registros:
        return None
    first = registros[0]
    if not getattr(first, "frente_servico", None):
        return None
    encarregado_nome = None
    if getattr(first.frente_servico, "encarregado", None):
        encarregado_nome = first.frente_servico.encarregado.nome
    return FrenteServicoSummary(
        id=first.frente_servico.id,
        nome=first.frente_servico.nome,
        encarregado=encarregado_nome,
    )


def _registro_to_schema(registro) -> RegistroOut:
    imagens = [
        ImagemOut(
            id=img.id,
            external_url=img.external_url,
            storage_path=img.storage_path,
            mime_type=img.mime_type,
            origem=img.origem,
        )
        for img in getattr(registro, "_imagens_cache", [])
    ]

    tempo_manha = registro.tempo_manha.value if hasattr(registro.tempo_manha, "value") else str(registro.tempo_manha)
    tempo_tarde = registro.tempo_tarde.value if hasattr(registro.tempo_tarde, "value") else str(registro.tempo_tarde)
    pista = registro.pista.value if hasattr(registro.pista, "value") else registro.pista
    lado_pista = registro.lado_pista.value if hasattr(registro.lado_pista, "value") else registro.lado_pista

    registrador_nome = registro.usuario_registrador.nome if getattr(registro, "usuario_registrador", None) else ""

    localizacao = {"tipo": "ESTACA"}
    if getattr(registro, "metadata_json", None) and isinstance(registro.metadata_json, dict):
        localizacao["tipo"] = registro.metadata_json.get("tipo", "ESTACA")
    localizacao["detalhe_texto"] = getattr(registro, "estaca", None)
    localizacao["valor_inicial"] = _to_float(registro.estaca_inicial) if registro.estaca_inicial is not None else None
    localizacao["valor_final"] = _to_float(registro.estaca_final) if registro.estaca_final is not None else None

    return RegistroOut(
        id=registro.id,
        data=registro.data,
        frente_servico_id=registro.frente_servico_id,
        usuario_registrador_id=registro.usuario_registrador_id,
        estaca_inicial=_to_float(registro.estaca_inicial),
        estaca_final=_to_float(registro.estaca_final),
        localizacao=localizacao,
        resultado=_to_float(registro.resultado),
        tempo_manha=tempo_manha,
        tempo_tarde=tempo_tarde,
        pista=pista,
        lado_pista=lado_pista,
        observacao=registro.observacao,
        created_at=registro.created_at,
        registrador_nome=registrador_nome,
        imagens=imagens,
    )


def _build_diario_do_dia_payload(data_alvo: date, registros: list) -> DiarioDoDiaOut:
    registros_out = [_registro_to_schema(item) for item in registros]
    total_resultado = round(sum(item.resultado for item in registros_out), 2)
    total_registros = len(registros_out)
    dias_impraticaveis = _is_dia_impraticavel(registros)
    resumo_clima = _build_resumo_clima(registros)

    return DiarioDoDiaOut(
        data=data_alvo,
        frente_servico=_frente_summary_from_registros(registros),
        registros=registros_out,
        total_resultado=total_resultado,
        total_registros=total_registros,
        dias_impraticaveis=dias_impraticaveis,
        resumo_clima=resumo_clima,
    )


@router.get(
    "/dia",
)
@require_auth
def obter_diario_do_dia():
    """summary: Diário de um dia; description: consulta por data e frente opcional; response_description: diário consolidado do dia."""
    try:
        data_alvo = _parse_date(request.args.get("data"), "data")
        frente_servico_id = _parse_optional_int(request.args.get("frente_servico_id"), "frente_servico_id")
    except ValueError as exc:
        return _json_error(str(exc), 422)

    with SessionLocal() as db:
        registros = get_diario_do_dia(
            db, 
            data=data_alvo, 
            frente_servico_id=frente_servico_id,
            tenant_id=getattr(g, "tenant_id", None)
        )

    if not registros:
        return _json_error("Não há registros para os filtros informados.", 404)

    payload = _build_diario_do_dia_payload(data_alvo, registros)
    return jsonify(payload.model_dump(mode="json"))


@router.get(
    "/periodo",
)
@require_auth
def obter_diario_periodo():
    """summary: Diário por período; description: consolida por dia com filtros opcionais; response_description: relatório completo do período."""
    try:
        data_inicio = _parse_date(request.args.get("data_inicio"), "data_inicio")
        data_fim = _parse_date(request.args.get("data_fim"), "data_fim")
        frente_servico_id = _parse_optional_int(request.args.get("frente_servico_id"), "frente_servico_id")
        usuario_id = _parse_optional_int(request.args.get("usuario_id"), "usuario_id")
        apenas_impraticaveis = _parse_bool(request.args.get("apenas_impraticaveis"))
    except ValueError as exc:
        return _json_error(str(exc), 422)

    if data_fim < data_inicio:
        return _json_error("data_fim não pode ser anterior a data_inicio.", 422)

    if (data_fim - data_inicio).days > 365:
        return _json_error("Período máximo permitido é de 365 dias.", 422)

    with SessionLocal() as db:
        registros = get_registros_por_periodo(
            db,
            data_inicio=data_inicio,
            data_fim=data_fim,
            frente_servico_id=frente_servico_id,
            usuario_id=usuario_id,
            tenant_id=getattr(g, "tenant_id", None),
            apenas_impraticaveis=apenas_impraticaveis,
        )

    grouped = agrupar_por_data(registros)
    dias = [_build_diario_do_dia_payload(day, items) for day, items in grouped.items()]

    total_resultado_periodo = round(sum(day.total_resultado for day in dias), 2)
    total_dias = len(dias)
    total_dias_impraticaveis = sum(1 for day in dias if day.dias_impraticaveis)
    media_diaria = round((total_resultado_periodo / total_dias), 2) if total_dias else 0.0

    payload = DiarioRelatorioOut(
        data_inicio=data_inicio,
        data_fim=data_fim,
        dias=dias,
        total_resultado_periodo=total_resultado_periodo,
        total_dias=total_dias,
        total_dias_impraticaveis=total_dias_impraticaveis,
        media_diaria=media_diaria,
    )
    return jsonify(payload.model_dump(mode="json"))


@router.get(
    "/exportar",
)
@require_auth
def exportar_diario_periodo():
    """summary: Exportar diário em JSON; description: mesmo payload de período com header para download/inline; response_description: JSON estruturado para exportação."""
    response_data = obter_diario_periodo()
    if isinstance(response_data, tuple):
        return response_data

    content = response_data.get_json()
    try:
        data_inicio = _parse_date(request.args.get("data_inicio"), "data_inicio")
        data_fim = _parse_date(request.args.get("data_fim"), "data_fim")
    except ValueError as exc:
        return _json_error(str(exc), 422)

    response = make_response(jsonify(content), 200)
    response.headers["Content-Disposition"] = (
        f'inline; filename="diario_{data_inicio.strftime("%Y%m%d")}_{data_fim.strftime("%Y%m%d")}.json"'
    )
    return response


@router.get(
    "/frentes",
)
@require_auth
def listar_frentes_diario():
    """summary: Frentes para filtros; description: lista frentes de serviço para filtros do diário; response_description: lista de frente com encarregado."""
    with SessionLocal() as db:
        frentes = Repository.frentes_servico.listar(db)

        payload = []
        for frente in frentes:
            encarregado_nome = frente.encarregado.nome if frente.encarregado else None
            payload.append(
                FrenteServicoSummary(
                    id=frente.id,
                    nome=frente.nome,
                    encarregado=encarregado_nome,
                ).model_dump(mode="json")
            )

    return jsonify(payload)
