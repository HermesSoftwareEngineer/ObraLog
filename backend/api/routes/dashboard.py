"""
Dashboard API — ObraLog
=======================
Retorna métricas, KPIs e séries temporais agregados por tenant para
alimentar painéis analíticos no frontend.

Todos os endpoints exigem autenticação (Bearer token).
Isolamento por tenant_id é aplicado em todas as queries.
"""

from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, request
from sqlalchemy import case, cast, func, text
from sqlalchemy.dialects.postgresql import INTERVAL
from sqlalchemy.types import Integer as SaInteger

from backend.api.routes.auth import require_auth
from backend.db.models import (
    Alert,
    AlertStatus,
    Clima,
    FrenteServico,
    MensagemCampo,
    Obra,
    Registro,
    RegistroStatus,
    Usuario,
)
from backend.db.session import SessionLocal

dashboard_blueprint = Blueprint("dashboard_v1", __name__, url_prefix="/api/v1/dashboard")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _date_range(days: int, end: date | None = None) -> tuple[date, date]:
    end = end or date.today()
    start = end - timedelta(days=days - 1)
    return start, end


# ---------------------------------------------------------------------------
# GET /api/v1/dashboard/overview
# ---------------------------------------------------------------------------

@dashboard_blueprint.get("/overview")
@require_auth
def overview():
    """
    Painel principal — KPIs e séries de 30 dias.

    Query params opcionais:
      - obra_id (int)    — filtra métricas por obra
      - days   (int, 7–365, default 30) — janela das séries temporais
    """
    tenant_id: int = g.tenant_id
    obra_id_param = request.args.get("obra_id", type=int)
    days_param = request.args.get("days", default=30, type=int)
    days_param = max(7, min(365, days_param))

    start_date, end_date = _date_range(days_param)

    with SessionLocal() as db:

        # ── Filtro base de registros ──────────────────────────────────────
        reg_q = db.query(Registro).filter(
            Registro.tenant_id == tenant_id,
            Registro.status != RegistroStatus.DESCARTADO,
        )
        if obra_id_param:
            reg_q = reg_q.filter(Registro.obra_id == obra_id_param)

        # ── KPIs gerais ───────────────────────────────────────────────────
        total_registros = reg_q.count()

        progresso_total = (
            db.query(func.coalesce(func.sum(Registro.resultado), 0))
            .filter(
                Registro.tenant_id == tenant_id,
                Registro.status != RegistroStatus.DESCARTADO,
                *([] if not obra_id_param else [Registro.obra_id == obra_id_param]),
            )
            .scalar()
        )

        total_usuarios = (
            db.query(func.count(Usuario.id))
            .filter(Usuario.tenant_id == tenant_id)
            .scalar()
        )

        total_frentes = (
            db.query(func.count(FrenteServico.id))
            .filter(FrenteServico.tenant_id == tenant_id)
            .scalar()
        )

        total_obras = (
            db.query(func.count(Obra.id))
            .filter(Obra.tenant_id == tenant_id, Obra.ativo == True)
            .scalar()
        )

        # ── Alertas ───────────────────────────────────────────────────────
        alert_base = db.query(Alert).filter(Alert.tenant_id == tenant_id)

        alertas_abertos = alert_base.filter(
            Alert.status.in_([AlertStatus.ABERTO, AlertStatus.EM_ATENDIMENTO, AlertStatus.AGUARDANDO_PECA])
        ).count()

        alertas_criticos = alert_base.filter(
            Alert.status.in_([AlertStatus.ABERTO, AlertStatus.EM_ATENDIMENTO, AlertStatus.AGUARDANDO_PECA]),
            Alert.severity.in_(["critica", "alta"]),
        ).count()

        alertas_nao_lidos = alert_base.filter(
            Alert.is_read == False,
            Alert.status != AlertStatus.CANCELADO,
        ).count()

        # ── Registros na janela ───────────────────────────────────────────
        registros_periodo = reg_q.filter(
            Registro.data >= start_date,
            Registro.data <= end_date,
        ).count()

        progresso_periodo = (
            db.query(func.coalesce(func.sum(Registro.resultado), 0))
            .filter(
                Registro.tenant_id == tenant_id,
                Registro.status != RegistroStatus.DESCARTADO,
                Registro.data >= start_date,
                Registro.data <= end_date,
                *([] if not obra_id_param else [Registro.obra_id == obra_id_param]),
            )
            .scalar()
        )

        # Dias impraticáveis na janela
        dias_impraticaveis = (
            db.query(func.count(func.distinct(Registro.data)))
            .filter(
                Registro.tenant_id == tenant_id,
                Registro.status != RegistroStatus.DESCARTADO,
                Registro.data >= start_date,
                Registro.data <= end_date,
                Registro.tempo_manha == Clima.IMPRATICAVEL,
                Registro.tempo_tarde == Clima.IMPRATICAVEL,
                *([] if not obra_id_param else [Registro.obra_id == obra_id_param]),
            )
            .scalar()
        )

        # ── Série: registros e progresso por dia ─────────────────────────
        daily_rows = (
            db.query(
                Registro.data.label("dia"),
                func.count(Registro.id).label("total_registros"),
                func.coalesce(func.sum(Registro.resultado), 0).label("progresso"),
                func.sum(
                    cast(
                        case(
                            (Registro.tempo_manha == Clima.IMPRATICAVEL, 1),
                            else_=0,
                        ),
                        SaInteger,
                    )
                ).label("impraticaveis_manha"),
                func.sum(
                    cast(
                        case(
                            (Registro.tempo_tarde == Clima.IMPRATICAVEL, 1),
                            else_=0,
                        ),
                        SaInteger,
                    )
                ).label("impraticaveis_tarde"),
            )
            .filter(
                Registro.tenant_id == tenant_id,
                Registro.status != RegistroStatus.DESCARTADO,
                Registro.data >= start_date,
                Registro.data <= end_date,
                *([] if not obra_id_param else [Registro.obra_id == obra_id_param]),
            )
            .group_by(Registro.data)
            .order_by(Registro.data)
            .all()
        )

        serie_diaria = [
            {
                "date": str(r.dia),
                "registros": r.total_registros,
                "progresso": float(r.progresso),
                "impraticaveis_manha": r.impraticaveis_manha,
                "impraticaveis_tarde": r.impraticaveis_tarde,
            }
            for r in daily_rows
        ]

        # ── Série: progresso por frente de serviço ────────────────────────
        frente_rows = (
            db.query(
                FrenteServico.id.label("frente_id"),
                FrenteServico.nome.label("frente_nome"),
                func.count(Registro.id).label("total_registros"),
                func.coalesce(func.sum(Registro.resultado), 0).label("progresso"),
            )
            .join(Registro, Registro.frente_servico_id == FrenteServico.id)
            .filter(
                Registro.tenant_id == tenant_id,
                Registro.status != RegistroStatus.DESCARTADO,
                Registro.data >= start_date,
                Registro.data <= end_date,
                *([] if not obra_id_param else [Registro.obra_id == obra_id_param]),
            )
            .group_by(FrenteServico.id, FrenteServico.nome)
            .order_by(func.sum(Registro.resultado).desc())
            .all()
        )

        progresso_por_frente = [
            {
                "frente_id": r.frente_id,
                "frente_nome": r.frente_nome,
                "total_registros": r.total_registros,
                "progresso": float(r.progresso),
            }
            for r in frente_rows
        ]

        # ── Distribuição de alertas por severidade ─────────────────────────
        sev_rows = (
            db.query(
                Alert.severity.label("sev"),
                func.count(Alert.id).label("total"),
            )
            .filter(
                Alert.tenant_id == tenant_id,
                Alert.status != AlertStatus.CANCELADO,
            )
            .group_by(Alert.severity)
            .all()
        )

        alertas_por_severidade = {r.sev: r.total for r in sev_rows}

        # ── Alertas por status ─────────────────────────────────────────────
        status_rows = (
            db.query(
                Alert.status.label("st"),
                func.count(Alert.id).label("total"),
            )
            .filter(Alert.tenant_id == tenant_id)
            .group_by(Alert.status)
            .all()
        )

        alertas_por_status = {r.st: r.total for r in status_rows}

        # ── Top 5 encarregados por produção no período ─────────────────────
        enc_rows = (
            db.query(
                Usuario.id.label("usuario_id"),
                Usuario.nome.label("usuario_nome"),
                func.count(Registro.id).label("total_registros"),
                func.coalesce(func.sum(Registro.resultado), 0).label("progresso"),
            )
            .join(Registro, Registro.usuario_registrador_id == Usuario.id)
            .filter(
                Registro.tenant_id == tenant_id,
                Registro.status != RegistroStatus.DESCARTADO,
                Registro.data >= start_date,
                Registro.data <= end_date,
                *([] if not obra_id_param else [Registro.obra_id == obra_id_param]),
            )
            .group_by(Usuario.id, Usuario.nome)
            .order_by(func.sum(Registro.resultado).desc())
            .limit(5)
            .all()
        )

        top_encarregados = [
            {
                "usuario_id": r.usuario_id,
                "usuario_nome": r.usuario_nome,
                "total_registros": r.total_registros,
                "progresso": float(r.progresso),
            }
            for r in enc_rows
        ]

        # ── Série de alertas abertos por dia ──────────────────────────────
        alert_daily_rows = (
            db.query(
                func.date(Alert.created_at).label("dia"),
                func.count(Alert.id).label("total"),
            )
            .filter(
                Alert.tenant_id == tenant_id,
                func.date(Alert.created_at) >= start_date,
                func.date(Alert.created_at) <= end_date,
            )
            .group_by(func.date(Alert.created_at))
            .order_by(func.date(Alert.created_at))
            .all()
        )

        alertas_por_dia = [
            {"date": str(r.dia), "total": r.total}
            for r in alert_daily_rows
        ]

        # ── Mensagens do agente na janela ─────────────────────────────────
        total_mensagens_periodo = (
            db.query(func.count(MensagemCampo.id))
            .filter(
                MensagemCampo.tenant_id == tenant_id,
                MensagemCampo.recebida_em >= datetime.combine(start_date, datetime.min.time()),
                MensagemCampo.recebida_em <= datetime.combine(end_date, datetime.max.time()),
                MensagemCampo.direcao == "user",
            )
            .scalar()
        )

    return jsonify({
        "ok": True,
        "periodo": {
            "inicio": str(start_date),
            "fim": str(end_date),
            "days": days_param,
        },
        "kpis": {
            # Totais globais (all-time)
            "usuarios_total": total_usuarios,
            "frentes_total": total_frentes,
            "obras_ativas": total_obras,
            "registros_total": total_registros,
            "progresso_total": float(progresso_total),
            # Alertas (snapshot atual)
            "alertas_abertos": alertas_abertos,
            "alertas_criticos": alertas_criticos,
            "alertas_nao_lidos": alertas_nao_lidos,
            # Período selecionado
            "registros_periodo": registros_periodo,
            "progresso_periodo": float(progresso_periodo),
            "dias_impraticaveis_periodo": dias_impraticaveis,
            "mensagens_agente_periodo": total_mensagens_periodo,
        },
        "charts": {
            "serie_diaria": serie_diaria,
            "progresso_por_frente": progresso_por_frente,
            "alertas_por_severidade": alertas_por_severidade,
            "alertas_por_status": alertas_por_status,
            "alertas_por_dia": alertas_por_dia,
            "top_encarregados": top_encarregados,
        },
    })


# ---------------------------------------------------------------------------
# GET /api/v1/dashboard/producao
# ---------------------------------------------------------------------------

@dashboard_blueprint.get("/producao")
@require_auth
def producao():
    """
    Análise detalhada de produção.

    Query params:
      - data_inicio (YYYY-MM-DD, obrigatório)
      - data_fim    (YYYY-MM-DD, obrigatório)
      - frente_id   (int, opcional)
      - obra_id     (int, opcional)
    """
    tenant_id: int = g.tenant_id

    data_inicio = _parse_date(request.args.get("data_inicio"))
    data_fim = _parse_date(request.args.get("data_fim"))
    frente_id_param = request.args.get("frente_id", type=int)
    obra_id_param = request.args.get("obra_id", type=int)

    if not data_inicio or not data_fim:
        return _json_error("data_inicio e data_fim são obrigatórios (YYYY-MM-DD)")
    if data_fim < data_inicio:
        return _json_error("data_fim não pode ser anterior a data_inicio")
    if (data_fim - data_inicio).days > 365:
        return _json_error("Período máximo de 365 dias")

    with SessionLocal() as db:

        base_filters = [
            Registro.tenant_id == tenant_id,
            Registro.status != RegistroStatus.DESCARTADO,
            Registro.data >= data_inicio,
            Registro.data <= data_fim,
        ]
        if frente_id_param:
            base_filters.append(Registro.frente_servico_id == frente_id_param)
        if obra_id_param:
            base_filters.append(Registro.obra_id == obra_id_param)

        # ── Resumo do período ──────────────────────────────────────────────
        totais = (
            db.query(
                func.count(Registro.id).label("total_registros"),
                func.coalesce(func.sum(Registro.resultado), 0).label("progresso"),
                func.count(func.distinct(Registro.data)).label("dias_trabalhados"),
                func.count(func.distinct(Registro.frente_servico_id)).label("frentes_ativas"),
                func.count(func.distinct(Registro.usuario_registrador_id)).label("encarregados_ativos"),
            )
            .filter(*base_filters)
            .one()
        )

        dias_impraticaveis = (
            db.query(func.count(func.distinct(Registro.data)))
            .filter(
                *base_filters,
                Registro.tempo_manha == Clima.IMPRATICAVEL,
                Registro.tempo_tarde == Clima.IMPRATICAVEL,
            )
            .scalar()
        )

        # ── Progresso acumulado por dia ────────────────────────────────────
        acumulado_rows = (
            db.query(
                Registro.data.label("dia"),
                func.coalesce(func.sum(Registro.resultado), 0).label("progresso_dia"),
            )
            .filter(*base_filters)
            .group_by(Registro.data)
            .order_by(Registro.data)
            .all()
        )

        progresso_acumulado = []
        acumulado = 0.0
        for r in acumulado_rows:
            acumulado += float(r.progresso_dia)
            progresso_acumulado.append({
                "date": str(r.dia),
                "progresso_dia": float(r.progresso_dia),
                "progresso_acumulado": round(acumulado, 4),
            })

        # ── Breakdown por frente ───────────────────────────────────────────
        frente_rows = (
            db.query(
                FrenteServico.id,
                FrenteServico.nome,
                func.count(Registro.id).label("registros"),
                func.coalesce(func.sum(Registro.resultado), 0).label("progresso"),
                func.count(func.distinct(Registro.data)).label("dias_ativos"),
            )
            .join(Registro, Registro.frente_servico_id == FrenteServico.id)
            .filter(*base_filters)
            .group_by(FrenteServico.id, FrenteServico.nome)
            .order_by(func.sum(Registro.resultado).desc())
            .all()
        )

        por_frente = [
            {
                "frente_id": r.id,
                "frente_nome": r.nome,
                "registros": r.registros,
                "progresso": float(r.progresso),
                "dias_ativos": r.dias_ativos,
                "media_diaria": round(float(r.progresso) / r.dias_ativos, 4) if r.dias_ativos else 0,
            }
            for r in frente_rows
        ]

        # ── Distribuição de clima ──────────────────────────────────────────
        clima_rows = (
            db.query(
                Registro.tempo_manha.label("clima"),
                func.count(Registro.id).label("total"),
            )
            .filter(*base_filters)
            .group_by(Registro.tempo_manha)
            .all()
        )

        clima_manha = {(r.clima or "nao_informado"): r.total for r in clima_rows}

        clima_tarde_rows = (
            db.query(
                Registro.tempo_tarde.label("clima"),
                func.count(Registro.id).label("total"),
            )
            .filter(*base_filters)
            .group_by(Registro.tempo_tarde)
            .all()
        )

        clima_tarde = {(r.clima or "nao_informado"): r.total for r in clima_tarde_rows}

        # ── Breakdown por lado de pista ────────────────────────────────────
        pista_rows = (
            db.query(
                Registro.lado_pista.label("lado"),
                func.count(Registro.id).label("registros"),
                func.coalesce(func.sum(Registro.resultado), 0).label("progresso"),
            )
            .filter(*base_filters)
            .group_by(Registro.lado_pista)
            .all()
        )

        por_pista = [
            {
                "lado": r.lado or "nao_informado",
                "registros": r.registros,
                "progresso": float(r.progresso),
            }
            for r in pista_rows
        ]

    progresso_total = float(totais.progresso)
    dias_trabalhados = totais.dias_trabalhados
    media_diaria = round(progresso_total / dias_trabalhados, 4) if dias_trabalhados else 0

    return jsonify({
        "ok": True,
        "periodo": {"inicio": str(data_inicio), "fim": str(data_fim)},
        "resumo": {
            "total_registros": totais.total_registros,
            "progresso_total": progresso_total,
            "dias_trabalhados": dias_trabalhados,
            "dias_impraticaveis": dias_impraticaveis,
            "frentes_ativas": totais.frentes_ativas,
            "encarregados_ativos": totais.encarregados_ativos,
            "media_diaria": media_diaria,
        },
        "charts": {
            "progresso_acumulado": progresso_acumulado,
            "por_frente": por_frente,
            "clima_manha": clima_manha,
            "clima_tarde": clima_tarde,
            "por_pista": por_pista,
        },
    })


# ---------------------------------------------------------------------------
# GET /api/v1/dashboard/alertas
# ---------------------------------------------------------------------------

@dashboard_blueprint.get("/alertas")
@require_auth
def alertas_analytics():
    """
    Análise de alertas operacionais.

    Query params opcionais:
      - days (int, 7–365, default 30)
      - obra_id (int)
    """
    tenant_id: int = g.tenant_id
    days_param = request.args.get("days", default=30, type=int)
    days_param = max(7, min(365, days_param))
    obra_id_param = request.args.get("obra_id", type=int)

    start_date, end_date = _date_range(days_param)

    with SessionLocal() as db:

        base = [Alert.tenant_id == tenant_id]
        periodo_filter = [
            *base,
            func.date(Alert.created_at) >= start_date,
            func.date(Alert.created_at) <= end_date,
        ]
        if obra_id_param:
            periodo_filter.append(Alert.obra_id == obra_id_param)

        # Totais no período
        total_periodo = db.query(func.count(Alert.id)).filter(*periodo_filter).scalar()

        resolvidos_periodo = (
            db.query(func.count(Alert.id))
            .filter(*periodo_filter, Alert.status == AlertStatus.RESOLVIDO)
            .scalar()
        )

        # Tempo médio de resolução (em horas) no período
        tempo_resolucao_row = (
            db.query(
                func.avg(
                    func.extract("epoch", Alert.resolved_at - Alert.created_at) / 3600
                ).label("media_horas")
            )
            .filter(
                *periodo_filter,
                Alert.status == AlertStatus.RESOLVIDO,
                Alert.resolved_at != None,
            )
            .one()
        )
        tempo_medio_resolucao_h = (
            round(float(tempo_resolucao_row.media_horas), 1)
            if tempo_resolucao_row.media_horas
            else None
        )

        # Por severidade no período
        sev_rows = (
            db.query(Alert.severity.label("sev"), func.count(Alert.id).label("total"))
            .filter(*periodo_filter)
            .group_by(Alert.severity)
            .all()
        )
        por_severidade = {r.sev: r.total for r in sev_rows}

        # Por tipo no período (top 10)
        tipo_rows = (
            db.query(Alert.type.label("tipo"), func.count(Alert.id).label("total"))
            .filter(*periodo_filter)
            .group_by(Alert.type)
            .order_by(func.count(Alert.id).desc())
            .limit(10)
            .all()
        )
        por_tipo = [{"tipo": r.tipo, "total": r.total} for r in tipo_rows]

        # Série diária no período
        serie_rows = (
            db.query(
                func.date(Alert.created_at).label("dia"),
                func.count(Alert.id).label("total"),
                func.sum(
                    cast(case((Alert.status == AlertStatus.RESOLVIDO, 1), else_=0), SaInteger)
                ).label("resolvidos"),
            )
            .filter(*periodo_filter)
            .group_by(func.date(Alert.created_at))
            .order_by(func.date(Alert.created_at))
            .all()
        )

        serie_diaria = [
            {"date": str(r.dia), "total": r.total, "resolvidos": r.resolvidos}
            for r in serie_rows
        ]

        # Snapshot atual — por status
        status_rows = (
            db.query(Alert.status.label("st"), func.count(Alert.id).label("total"))
            .filter(*base)
            .group_by(Alert.status)
            .all()
        )
        por_status_snapshot = {r.st: r.total for r in status_rows}

        # Alertas abertos por criticidade (para badge)
        abertos_criticos = (
            db.query(func.count(Alert.id))
            .filter(
                *base,
                Alert.status.in_([AlertStatus.ABERTO, AlertStatus.EM_ATENDIMENTO]),
                Alert.severity.in_(["critica", "alta"]),
            )
            .scalar()
        )

    taxa_resolucao = round(resolvidos_periodo / total_periodo * 100, 1) if total_periodo else 0

    return jsonify({
        "ok": True,
        "periodo": {"inicio": str(start_date), "fim": str(end_date), "days": days_param},
        "kpis": {
            "total_periodo": total_periodo,
            "resolvidos_periodo": resolvidos_periodo,
            "taxa_resolucao_pct": taxa_resolucao,
            "tempo_medio_resolucao_horas": tempo_medio_resolucao_h,
            "abertos_criticos_atual": abertos_criticos,
        },
        "charts": {
            "por_severidade": por_severidade,
            "por_tipo": por_tipo,
            "por_status_snapshot": por_status_snapshot,
            "serie_diaria": serie_diaria,
        },
    })


# ---------------------------------------------------------------------------
# GET /api/v1/dashboard/equipe
# ---------------------------------------------------------------------------

@dashboard_blueprint.get("/equipe")
@require_auth
def equipe():
    """
    Métricas de engajamento e produtividade por usuário.

    Query params opcionais:
      - days (int, 7–365, default 30)
    """
    tenant_id: int = g.tenant_id
    days_param = request.args.get("days", default=30, type=int)
    days_param = max(7, min(365, days_param))
    start_date, end_date = _date_range(days_param)

    with SessionLocal() as db:

        # Headcount por nível
        nivel_rows = (
            db.query(
                Usuario.nivel_acesso.label("nivel"),
                func.count(Usuario.id).label("total"),
            )
            .filter(Usuario.tenant_id == tenant_id)
            .group_by(Usuario.nivel_acesso)
            .all()
        )
        por_nivel = {str(r.nivel): r.total for r in nivel_rows}

        # Usuários com Telegram vinculado
        com_telegram = (
            db.query(func.count(Usuario.id))
            .filter(
                Usuario.tenant_id == tenant_id,
                Usuario.telegram_chat_id != None,
            )
            .scalar()
        )

        total_usuarios = sum(por_nivel.values())

        # Ranking por produção no período
        ranking_rows = (
            db.query(
                Usuario.id.label("usuario_id"),
                Usuario.nome.label("nome"),
                Usuario.nivel_acesso.label("nivel"),
                func.count(Registro.id).label("registros"),
                func.coalesce(func.sum(Registro.resultado), 0).label("progresso"),
                func.count(func.distinct(Registro.data)).label("dias_ativos"),
            )
            .outerjoin(
                Registro,
                (Registro.usuario_registrador_id == Usuario.id)
                & (Registro.tenant_id == tenant_id)
                & (Registro.status != RegistroStatus.DESCARTADO)
                & (Registro.data >= start_date)
                & (Registro.data <= end_date),
            )
            .filter(
                Usuario.tenant_id == tenant_id,
                Usuario.nivel_acesso == "encarregado",
            )
            .group_by(Usuario.id, Usuario.nome, Usuario.nivel_acesso)
            .order_by(func.sum(Registro.resultado).desc().nulls_last())
            .all()
        )

        ranking = [
            {
                "usuario_id": r.usuario_id,
                "nome": r.nome,
                "nivel": str(r.nivel),
                "registros": r.registros,
                "progresso": float(r.progresso or 0),
                "dias_ativos": r.dias_ativos,
                "telegram_vinculado": False,  # preenchido abaixo
            }
            for r in ranking_rows
        ]

        # Marcar quem tem Telegram
        telegram_ids = {
            u.id
            for u in db.query(Usuario.id).filter(
                Usuario.tenant_id == tenant_id,
                Usuario.telegram_chat_id != None,
            )
        }
        for item in ranking:
            item["telegram_vinculado"] = item["usuario_id"] in telegram_ids

        # Atividade por dia de semana (0=seg, 6=dom)
        dow_rows = (
            db.query(
                func.extract("dow", Registro.data).label("dow"),
                func.count(Registro.id).label("registros"),
                func.coalesce(func.sum(Registro.resultado), 0).label("progresso"),
            )
            .filter(
                Registro.tenant_id == tenant_id,
                Registro.status != RegistroStatus.DESCARTADO,
                Registro.data >= start_date,
                Registro.data <= end_date,
            )
            .group_by(func.extract("dow", Registro.data))
            .order_by(func.extract("dow", Registro.data))
            .all()
        )

        _dow_names = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
        atividade_semanal = [
            {
                "dow": int(r.dow),
                "nome": _dow_names[int(r.dow)],
                "registros": r.registros,
                "progresso": float(r.progresso),
            }
            for r in dow_rows
        ]

    return jsonify({
        "ok": True,
        "periodo": {"inicio": str(start_date), "fim": str(end_date), "days": days_param},
        "kpis": {
            "total_usuarios": total_usuarios,
            "com_telegram_vinculado": com_telegram,
            "pct_telegram_vinculado": round(com_telegram / total_usuarios * 100, 1) if total_usuarios else 0,
            "por_nivel": por_nivel,
        },
        "charts": {
            "ranking_encarregados": ranking,
            "atividade_por_dia_semana": atividade_semanal,
        },
    })
