from __future__ import annotations

from datetime import date
from decimal import Decimal

from flask import Blueprint, jsonify, make_response, request, g, send_file

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
from backend.db.models import DiarioVersao, NivelAcesso


router = Blueprint("diario_v1", __name__, url_prefix="/api/v1/diario")
diarios_router = Blueprint("diarios_v1", __name__, url_prefix="/api/v1/diarios")
diarios_files_router = Blueprint("diarios_files_v1", __name__, url_prefix="/api/v1/diarios-files")


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
    localizacao["detalhe_texto"] = getattr(registro, "localizacao", None)
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


# ---------------------------------------------------------------------------
# Diários persistidos — geração, versionamento e consulta
# ---------------------------------------------------------------------------

_NIVEL_GERENTE_ADMIN = {NivelAcesso.ADMINISTRADOR.value, NivelAcesso.GERENTE.value}


def _check_gerente_admin():
    """Returns (user, None) if access is granted, or (None, error_response) if denied."""
    user = getattr(g, "current_user", None)
    if not user:
        return None, (_json_error("Usuário não autenticado.", 401))
    nivel = user.nivel_acesso.value if hasattr(user.nivel_acesso, "value") else str(user.nivel_acesso)
    if nivel not in _NIVEL_GERENTE_ADMIN:
        return None, (_json_error("Acesso restrito a gerentes e administradores.", 403))
    return user, None


@diarios_router.get("/imagens/<int:imagem_id>")
def servir_imagem_registro(imagem_id: int):
    """Serve a registro image by ID. No auth required — browsers load <img> without headers.
    Consistent with the PDF file-serving endpoint (servir_pdf_local)."""
    from flask import redirect, send_file
    from backend.db.models import RegistroImagem
    with SessionLocal() as db:
        img = db.query(RegistroImagem).filter(RegistroImagem.id == imagem_id).first()
        if not img:
            return _json_error("Imagem não encontrada.", 404)
        if img.external_url:
            return redirect(img.external_url)
        if img.storage_path:
            from pathlib import Path
            p = Path(img.storage_path)
            if p.exists():
                return send_file(str(p.resolve()), mimetype=img.mime_type or "image/jpeg")
        return _json_error("Arquivo de imagem não disponível.", 404)


@diarios_router.post("/gerar")
@require_auth
def gerar_diario():
    """Gera ou regera um diário para a obra/período. Requer gerente ou administrador."""
    user, err = _check_gerente_admin()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    try:
        obra_id = int(data["obra_id"])
        tipo = str(data.get("tipo", "diario")).strip()
        data_inicio = date.fromisoformat(data["data_inicio"])
        data_fim = date.fromisoformat(data["data_fim"])
    except (KeyError, ValueError, TypeError) as exc:
        return _json_error(f"Parâmetros inválidos: {exc}", 422)

    if tipo not in ("diario", "semanal", "mensal"):
        return _json_error("tipo deve ser 'diario', 'semanal' ou 'mensal'.", 422)
    if data_fim < data_inicio:
        return _json_error("data_fim não pode ser anterior a data_inicio.", 422)

    tenant_id = getattr(g, "tenant_id", None)
    if tenant_id is None:
        return _json_error("Tenant não identificado.", 400)

    motivo = str(data["motivo_regeracao"]).strip() if data.get("motivo_regeracao") else None
    include_pending = bool(data.get("include_pending", False))

    try:
        from backend.services.diario_service import gerar_ou_regerar_diario
        result = gerar_ou_regerar_diario(
            obra_id=obra_id,
            tenant_id=tenant_id,
            tipo=tipo,
            data_inicio=data_inicio,
            data_fim=data_fim,
            gerado_por=user.id,
            motivo_regeracao=motivo,
            include_pending=include_pending,
        )
        return jsonify(result), 201
    except ValueError as exc:
        return _json_error(str(exc), 404)
    except RuntimeError as exc:
        return _json_error(str(exc), 502)


@diarios_router.post("/<string:diario_id>/finalizar")
@require_auth
def finalizar_diario(diario_id: str):
    """Finaliza um diário. Requer gerente ou administrador."""
    user, err = _check_gerente_admin()
    if err:
        return err

    tenant_id = getattr(g, "tenant_id", None)
    try:
        from backend.services.diario_service import finalizar_diario as _finalizar
        result = _finalizar(diario_id=diario_id, finalizado_por=user.id, tenant_id=tenant_id)
        return jsonify(result)
    except ValueError as exc:
        return _json_error(str(exc), 404)


@diarios_router.get("")
@require_auth
def listar_diarios():
    """Lista diários do tenant com filtros opcionais e paginação."""
    obra_id_raw = request.args.get("obra_id")
    tipo = request.args.get("tipo")
    status = request.args.get("status")
    data_inicio_raw = request.args.get("data_inicio")
    data_fim_raw = request.args.get("data_fim")

    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    except (TypeError, ValueError):
        return _json_error("Parâmetros de paginação inválidos.", 422)

    tenant_id = getattr(g, "tenant_id", None)

    try:
        from backend.db.models import Diario
        from backend.services.diario_service import _diario_to_dict
        with SessionLocal() as db:
            q = db.query(Diario).filter(Diario.tenant_id == tenant_id)
            if obra_id_raw:
                try:
                    obra_id = int(obra_id_raw)
                except (TypeError, ValueError):
                    return _json_error("obra_id deve ser um número inteiro.", 422)
                q = q.filter(Diario.obra_id == obra_id)
            if tipo:
                q = q.filter(Diario.tipo == tipo)
            if status:
                q = q.filter(Diario.status == status)
            if data_inicio_raw:
                q = q.filter(Diario.data_inicio >= date.fromisoformat(data_inicio_raw))
            if data_fim_raw:
                q = q.filter(Diario.data_fim <= date.fromisoformat(data_fim_raw))
            total = q.count()
            diarios = (
                q.order_by(Diario.data_inicio.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
            payload = [_diario_to_dict(d) for d in diarios]
        return jsonify({
            "items": payload,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
        })
    except ValueError as exc:
        return _json_error(f"Parâmetro de data inválido: {exc}", 422)


@diarios_router.get("/<string:diario_id>")
@require_auth
def obter_diario(diario_id: str):
    """Retorna um diário específico com todas as versões."""
    tenant_id = getattr(g, "tenant_id", None)
    from backend.db.models import Diario, DiarioVersao as DV
    with SessionLocal() as db:
        diario = db.query(Diario).filter(
            Diario.id == diario_id,
            Diario.tenant_id == tenant_id,
        ).first()
        if not diario:
            return _json_error("Diário não encontrado.", 404)
        versoes = (
            db.query(DV)
            .filter(DV.diario_id == diario.id)
            .order_by(DV.versao.desc())
            .all()
        )
        from backend.services.diario_service import _diario_to_dict, _versao_to_dict
        return jsonify(_diario_to_dict(diario, versoes))


@diarios_router.delete("/<string:diario_id>")
@require_auth
def deletar_diario(diario_id: str):
    """Exclui um diário e todas as suas versões. Requer gerente ou administrador."""
    _, err = _check_gerente_admin()
    if err:
        return err
    tenant_id = getattr(g, "tenant_id", None)
    try:
        from backend.services.diario_service import deletar_diario as _deletar
        _deletar(diario_id=diario_id, tenant_id=tenant_id)
        return jsonify({"ok": True})
    except ValueError as exc:
        return _json_error(str(exc), 404)


@diarios_router.get("/<string:diario_id>/versoes/<int:versao>/dados")
@require_auth
def obter_dados_versao(diario_id: str, versao: int):
    """Retorna todos os dados de uma versão para visualização no frontend."""
    tenant_id = getattr(g, "tenant_id", None)
    try:
        from backend.services.diario_service import get_dados_para_exportar
        diario_info, registros_rows, frentes_schemas = get_dados_para_exportar(diario_id, versao, tenant_id)
    except ValueError as exc:
        return _json_error(str(exc), 404)

    from backend.db.models import Diario, DiarioVersao as DV
    with SessionLocal() as db:
        diario = db.query(Diario).filter(
            Diario.id == diario_id, Diario.tenant_id == tenant_id
        ).first()
        versoes = (
            db.query(DV)
            .filter(DV.diario_id == diario_id)
            .order_by(DV.versao.desc())
            .all()
        )
        from backend.services.diario_service import _diario_to_dict
        diario_dict = _diario_to_dict(diario, versoes) if diario else None

    return jsonify({
        "diario": diario_dict,
        "diario_info": diario_info,
        "registros": registros_rows,
        "frentes_schemas": frentes_schemas,
    })


@diarios_router.get("/<string:diario_id>/versoes/<int:versao>/url")
@require_auth
def obter_url_versao(diario_id: str, versao: int):
    """Retorna a signed URL do PDF de uma versão específica (válida por 1 hora)."""
    tenant_id = getattr(g, "tenant_id", None)
    from backend.db.models import DiarioVersao as DV
    with SessionLocal() as db:
        versao_obj = db.query(DV).filter(
            DV.diario_id == diario_id,
            DV.versao == versao,
            DV.tenant_id == tenant_id,
        ).first()
        if not versao_obj:
            return _json_error("Versão não encontrada.", 404)
        storage_path = versao_obj.storage_path

    from backend.utils.storage import get_signed_url_diario
    url = get_signed_url_diario(storage_path, expires_in=3600)
    if not url:
        return _json_error("Não foi possível gerar a URL de download.", 502)
    return jsonify({"url": url})


@diarios_router.get("/<string:diario_id>/versoes/<int:versao>/exportar/excel")
@require_auth
def exportar_excel(diario_id: str, versao: int):
    """Exporta registros de uma versão como planilha Excel."""
    tenant_id = getattr(g, "tenant_id", None)
    try:
        from backend.services.diario_service import get_dados_para_exportar
        diario_info, registros_rows, frentes_schemas = get_dados_para_exportar(diario_id, versao, tenant_id)
    except ValueError as exc:
        return _json_error(str(exc), 404)

    try:
        from backend.services.excel_service import gerar_excel_diario
        xlsx_bytes = gerar_excel_diario(diario_info, registros_rows, frentes_schemas)
    except Exception as exc:
        return _json_error(f"Falha ao gerar Excel: {exc}", 502)

    obra_nome = (diario_info.get("obra_nome") or "obra").replace(" ", "_")
    filename = f"diario_{obra_nome}_v{versao}.xlsx"
    response = make_response(xlsx_bytes)
    response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@diarios_router.get("/<string:diario_id>/versoes/<int:versao>/exportar/word")
@require_auth
def exportar_word(diario_id: str, versao: int):
    """Exporta registros de uma versão como documento Word."""
    tenant_id = getattr(g, "tenant_id", None)
    try:
        from backend.services.diario_service import get_dados_para_exportar
        diario_info, registros_rows, frentes_schemas = get_dados_para_exportar(diario_id, versao, tenant_id)
    except ValueError as exc:
        return _json_error(str(exc), 404)

    try:
        from backend.services.word_service import gerar_word_diario
        docx_bytes = gerar_word_diario(diario_info, registros_rows, frentes_schemas)
    except Exception as exc:
        return _json_error(f"Falha ao gerar Word: {exc}", 502)

    obra_nome = (diario_info.get("obra_nome") or "obra").replace(" ", "_")
    filename = f"diario_{obra_nome}_v{versao}.docx"
    response = make_response(docx_bytes)
    response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@diarios_files_router.get("/<path:file_path>")
def servir_pdf_local(file_path: str):
    """Serve PDFs salvos localmente (fallback quando Supabase não está configurado)."""
    from backend.utils.storage import get_local_pdf_path
    abs_path = get_local_pdf_path(f"local/{file_path}")
    if abs_path is None or not abs_path.exists():
        return _json_error("Arquivo não encontrado.", 404)
    return send_file(str(abs_path), mimetype="application/pdf")
