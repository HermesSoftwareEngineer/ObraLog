from __future__ import annotations

from datetime import datetime
from uuid import UUID
import unicodedata

from flask import Blueprint, g, jsonify, request
from sqlalchemy import desc, func

from backend.api.routes.auth import require_auth
from backend.db.models import Alert, AlertRead, AlertSeverity, AlertStatus, AlertType, NivelAcesso
from backend.db.session import SessionLocal


router = Blueprint("alerts_v1", __name__, url_prefix="/api/v1/alertas")


def _json_error(message: str, status_code: int = 400):
    return jsonify({"ok": False, "error": message}), status_code


def _to_json_value(value):
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _to_dict(model_instance):
    payload = {}
    for key in model_instance.__table__.columns.keys():
        payload[key] = _to_json_value(getattr(model_instance, key))
    return payload


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.strip().lower().split())


def _parse_alert_type(value: str) -> AlertType:
    aliases = {
        "maquina quebrada": AlertType.MAQUINA_QUEBRADA,
        "maquina_quebrada": AlertType.MAQUINA_QUEBRADA,
        "acidente": AlertType.ACIDENTE,
        "falta material": AlertType.FALTA_MATERIAL,
        "falta_material": AlertType.FALTA_MATERIAL,
        "risco seguranca": AlertType.RISCO_SEGURANCA,
        "risco_seguranca": AlertType.RISCO_SEGURANCA,
        "outro": AlertType.OUTRO,
    }
    parsed = aliases.get(_normalize_text(value))
    if parsed is None:
        raise ValueError("type inválido. Use: maquina_quebrada, acidente, falta_material, risco_seguranca, outro.")
    return parsed


def _parse_alert_severity(value: str) -> AlertSeverity:
    aliases = {
        "baixa": AlertSeverity.BAIXA,
        "media": AlertSeverity.MEDIA,
        "alta": AlertSeverity.ALTA,
        "critica": AlertSeverity.CRITICA,
    }
    parsed = aliases.get(_normalize_text(value))
    if parsed is None:
        raise ValueError("severity inválido. Use: baixa, media, alta, critica.")
    return parsed


def _parse_alert_status(value: str) -> AlertStatus:
    aliases = {
        "aberto": AlertStatus.ABERTO,
        "em atendimento": AlertStatus.EM_ATENDIMENTO,
        "em_atendimento": AlertStatus.EM_ATENDIMENTO,
        "aguardando peca": AlertStatus.AGUARDANDO_PECA,
        "aguardando_peca": AlertStatus.AGUARDANDO_PECA,
        "resolvido": AlertStatus.RESOLVIDO,
        "cancelado": AlertStatus.CANCELADO,
    }
    parsed = aliases.get(_normalize_text(value))
    if parsed is None:
        raise ValueError("status inválido. Use: aberto, em_atendimento, aguardando_peca, resolvido, cancelado.")
    return parsed


def _default_alert_description(
    alert_type: AlertType,
    location_detail: str | None = None,
    equipment_name: str | None = None,
) -> str:
    base_by_type = {
        AlertType.MAQUINA_QUEBRADA: "Máquina/equipamento com falha operacional",
        AlertType.ACIDENTE: "Ocorrência de acidente em campo",
        AlertType.FALTA_MATERIAL: "Ocorrência de falta de material",
        AlertType.RISCO_SEGURANCA: "Ocorrência de risco de segurança",
        AlertType.OUTRO: "Ocorrência operacional reportada",
    }
    parts = [base_by_type.get(alert_type, "Ocorrência operacional reportada")]
    if location_detail:
        parts.append(f"Local: {location_detail}")
    if equipment_name:
        parts.append(f"Equipamento: {equipment_name}")
    return ". ".join(parts)


def _is_admin_or_gerente() -> bool:
    nivel = g.current_user.nivel_acesso.value if hasattr(g.current_user.nivel_acesso, "value") else str(g.current_user.nivel_acesso)
    return nivel in {NivelAcesso.ADMINISTRADOR.value, NivelAcesso.GERENTE.value}


def _generate_alert_code(db) -> str:
    year = datetime.utcnow().year
    prefix = f"ALT-{year}-"
    count = db.query(func.count(Alert.id)).filter(Alert.code.like(f"{prefix}%")).scalar() or 0
    return f"{prefix}{count + 1:04d}"


def _sync_alert_read_flags(db, alert):
    latest_read = (
        db.query(AlertRead)
        .filter(AlertRead.alert_id == alert.id)
        .order_by(desc(AlertRead.read_at))
        .first()
    )
    if latest_read:
        alert.is_read = True
        alert.read_at = latest_read.read_at
        alert.read_by = latest_read.worker_id
    else:
        alert.is_read = False
        alert.read_at = None
        alert.read_by = None


@router.get("")
@require_auth
def listar_alertas():
    with SessionLocal() as db:
        query = db.query(Alert)

        status = request.args.get("status")
        severity = request.args.get("severity")
        apenas_nao_lidos = request.args.get("apenas_nao_lidos", "false").lower() in {"1", "true", "yes", "on"}

        if status:
            try:
                query = query.filter(Alert.status == _parse_alert_status(status))
            except ValueError as exc:
                return _json_error(str(exc), 422)

        if severity:
            try:
                query = query.filter(Alert.severity == _parse_alert_severity(severity))
            except ValueError as exc:
                return _json_error(str(exc), 422)

        if apenas_nao_lidos:
            query = query.filter(Alert.is_read.is_(False))

        items = query.order_by(Alert.created_at.desc()).limit(200).all()
        return jsonify({"ok": True, "total": len(items), "alertas": [_to_dict(item) for item in items]})


@router.post("")
@require_auth
def criar_alerta():
    data = request.get_json(silent=True) or {}
    try:
        title = data["title"]
        type_value = _parse_alert_type(data["type"])
        severity_value = _parse_alert_severity(data["severity"])
    except KeyError as exc:
        return _json_error(f"Campo obrigatório ausente: {exc.args[0]}")
    except ValueError as exc:
        return _json_error(str(exc), 422)

    description = (data.get("description") or "").strip()
    if not description:
        description = _default_alert_description(
            alert_type=type_value,
            location_detail=(data.get("location_detail") or "").strip() or None,
            equipment_name=(data.get("equipment_name") or "").strip() or None,
        )

    with SessionLocal() as db:
        alert = Alert(
            code=_generate_alert_code(db),
            type=type_value,
            severity=severity_value,
            reported_by=g.current_user.id,
            telegram_message_id=data.get("telegram_message_id"),
            title=title,
            description=description,
            raw_text=data.get("raw_text"),
            location_detail=data.get("location_detail"),
            equipment_name=data.get("equipment_name"),
            photo_urls=data.get("photo_urls"),
            status=AlertStatus.ABERTO,
            priority_score=data.get("priority_score"),
            notified_channels=data.get("notified_channels"),
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return jsonify({"ok": True, "alerta": _to_dict(alert)}), 201


@router.get("/<uuid:alert_id>")
@require_auth
def obter_alerta(alert_id):
    with SessionLocal() as db:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return _json_error("Alerta não encontrado.", 404)
        return jsonify({"ok": True, "alerta": _to_dict(alert)})


@router.patch("/<uuid:alert_id>/status")
@require_auth
def atualizar_status_alerta(alert_id):
    if not _is_admin_or_gerente():
        return _json_error("Apenas administrador/gerente pode atualizar status do alerta.", 403)

    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if not status:
        return _json_error("Campo obrigatório: status")

    try:
        parsed_status = _parse_alert_status(status)
    except ValueError as exc:
        return _json_error(str(exc), 422)

    with SessionLocal() as db:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return _json_error("Alerta não encontrado.", 404)

        alert.status = parsed_status
        alert.resolution_notes = data.get("resolution_notes")
        if parsed_status in {AlertStatus.RESOLVIDO, AlertStatus.CANCELADO}:
            alert.resolved_by = g.current_user.id
            alert.resolved_at = datetime.utcnow()

        db.commit()
        db.refresh(alert)
        return jsonify({"ok": True, "alerta": _to_dict(alert)})


@router.post("/<uuid:alert_id>/read")
@require_auth
def marcar_como_lido(alert_id):
    with SessionLocal() as db:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return _json_error("Alerta não encontrado.", 404)

        read = (
            db.query(AlertRead)
            .filter(AlertRead.alert_id == alert_id)
            .filter(AlertRead.worker_id == g.current_user.id)
            .first()
        )
        if not read:
            read = AlertRead(alert_id=alert_id, worker_id=g.current_user.id)
            db.add(read)

        alert.is_read = True
        alert.read_at = datetime.utcnow()
        alert.read_by = g.current_user.id

        db.commit()
        db.refresh(alert)
        db.refresh(read)
        return jsonify({"ok": True, "alerta": _to_dict(alert), "leitura": _to_dict(read)})


@router.post("/<uuid:alert_id>/unread")
@require_auth
def marcar_como_nao_lido(alert_id):
    with SessionLocal() as db:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return _json_error("Alerta não encontrado.", 404)

        read = (
            db.query(AlertRead)
            .filter(AlertRead.alert_id == alert_id)
            .filter(AlertRead.worker_id == g.current_user.id)
            .first()
        )
        if not read:
            return jsonify({"ok": True, "message": "Alerta já estava como não lido para este usuário.", "alerta": _to_dict(alert)})

        db.delete(read)
        _sync_alert_read_flags(db, alert)

        db.commit()
        db.refresh(alert)
        return jsonify({"ok": True, "alerta": _to_dict(alert)})
