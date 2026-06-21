"""Serviço de alertas operacionais."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from backend.agents.tools.database.common import (
    assert_permission,
    default_alert_description,
    default_alert_title,
    generate_alert_code,
    normalize_text,
    parse_alert_severity,
    parse_alert_status,
    parse_alert_type,
    to_dict,
)
from backend.db.models import Alert, AlertRead, AlertStatus, AlertTypeAlias
from backend.db.repository import Repository
from backend.db.session import SessionLocal

logger = logging.getLogger("obralog.services.alerta")


def _resolve_tenant(db, tenant_id: int) -> int:
    if tenant_id is not None:
        return int(tenant_id)
    return int(Repository.tenants.get_default(db).id)


def _get_alert(db, tenant_id: int, alert_id: str | None, alert_code: str | None) -> Alert | None:
    if alert_id:
        return db.query(Alert).filter(Alert.id == uuid.UUID(alert_id), Alert.tenant_id == tenant_id).first()
    if alert_code:
        return db.query(Alert).filter(Alert.code == str(alert_code).strip(), Alert.tenant_id == tenant_id).first()
    raise ValueError("Informe alert_id ou alert_code para identificar o alerta.")


def _resolve_alert_type(db, tenant_id: int, value: str) -> str:
    normalized = normalize_text((value or "").replace("_", " "))
    alias = (
        db.query(AlertTypeAlias)
        .filter(
            AlertTypeAlias.normalized_alias == normalized,
            AlertTypeAlias.ativo.is_(True),
            AlertTypeAlias.tenant_id == tenant_id,
        )
        .first()
    )
    if alias:
        return str(alias.canonical_type)
    return parse_alert_type(value)


def criar_alerta(
    tenant_id: int,
    actor_user_id: int,
    actor_level: str,
    *,
    type: str,
    description: str | None = None,
    severity: str | None = None,
    title: str | None = None,
    obra_id: int | None = None,
    raw_text: str | None = None,
    location_detail: str | None = None,
    equipment_name: str | None = None,
    photo_urls: list[str] | None = None,
    telegram_message_id: int | None = None,
    notified_channels: list[str] | None = None,
) -> dict:
    assert_permission(actor_level, "create", "alerts")
    with SessionLocal() as db:
        effective_tid = _resolve_tenant(db, tenant_id)
        if obra_id is not None:
            obra = Repository.obras.obter_por_id(db, int(obra_id), tenant_id=effective_tid)
            if not obra:
                raise ValueError("obra_id inválido para este tenant.")

        alert_type = _resolve_alert_type(db, effective_tid, type)
        alert_severity = parse_alert_severity(severity)
        normalized_desc = (description or "").strip()
        used_suggestion = not bool(normalized_desc)
        if not normalized_desc:
            normalized_desc = default_alert_description(
                alert_type=alert_type,
                location_detail=(location_detail or "").strip() or None,
                equipment_name=(equipment_name or "").strip() or None,
            )

        alert = Alert(
            tenant_id=effective_tid,
            code=generate_alert_code(db, tenant_id=effective_tid),
            type=alert_type,
            severity=alert_severity,
            reported_by=actor_user_id,
            obra_id=int(obra_id) if obra_id is not None else None,
            telegram_message_id=telegram_message_id,
            title=(title or "").strip() or default_alert_title(alert_type),
            description=normalized_desc,
            raw_text=raw_text,
            location_detail=location_detail,
            equipment_name=equipment_name,
            photo_urls=photo_urls,
            status=AlertStatus.ABERTO,
            notified_channels=notified_channels,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        payload = {"ok": True, "alerta": to_dict(alert)}
        if used_suggestion:
            payload["description_sugerida"] = normalized_desc
        return payload


def obter_alerta(
    tenant_id: int,
    actor_user_id: int,
    actor_level: str,
    alert_id: str | None,
    alert_code: str | None,
) -> dict:
    assert_permission(actor_level, "read", "alerts")
    with SessionLocal() as db:
        effective_tid = _resolve_tenant(db, tenant_id)
        alert = _get_alert(db, effective_tid, alert_id, alert_code)
        if not alert:
            return {"ok": False, "message": "Alerta não encontrado."}
        return {"ok": True, "alerta": to_dict(alert)}


def listar_alertas(
    tenant_id: int,
    actor_user_id: int,
    actor_level: str,
    *,
    status: str | None = None,
    severity: str | None = None,
    obra_id: int | None = None,
    apenas_nao_lidos: bool = False,
    limit: int = 50,
) -> dict:
    assert_permission(actor_level, "read", "alerts")
    with SessionLocal() as db:
        effective_tid = _resolve_tenant(db, tenant_id)
        query = db.query(Alert).filter(Alert.tenant_id == effective_tid)
        if status:
            query = query.filter(Alert.status == parse_alert_status(status))
        if severity:
            query = query.filter(Alert.severity == parse_alert_severity(severity))
        if obra_id is not None:
            query = query.filter(Alert.obra_id == int(obra_id))
        if apenas_nao_lidos:
            read_subq = (
                db.query(AlertRead.alert_id)
                .filter(AlertRead.worker_id == actor_user_id, AlertRead.tenant_id == effective_tid)
                .subquery()
            )
            query = query.filter(~Alert.id.in_(read_subq))
        items = query.order_by(Alert.created_at.desc()).limit(max(1, min(limit, 200))).all()
        if not items:
            return {
                "ok": True, "total": 0, "alertas": [],
                "message": "Nenhum alerta encontrado para os filtros informados.",
                "next_steps": ["consultar outro status", "consultar outra severidade"],
            }
        return {"ok": True, "total": len(items), "alertas": [to_dict(i) for i in items]}


def atualizar_alerta(
    tenant_id: int,
    actor_user_id: int,
    actor_level: str,
    alert_id: str | None,
    alert_code: str | None,
    *,
    status: str | None = None,
    resolution_notes: str | None = None,
    type: str | None = None,
    severity: str | None = None,
    obra_id: int | None = None,
    title: str | None = None,
    description: str | None = None,
    location_detail: str | None = None,
    equipment_name: str | None = None,
    photo_urls: list[str] | None = None,
    notified_channels: list[str] | None = None,
) -> dict:
    assert_permission(actor_level, "update", "alerts")
    new_status = parse_alert_status(status) if status and str(status).strip() else None

    with SessionLocal() as db:
        effective_tid = _resolve_tenant(db, tenant_id)
        alert = _get_alert(db, effective_tid, alert_id, alert_code)
        if not alert:
            return {"ok": False, "message": "Alerta não encontrado."}

        if type is not None:
            alert.type = _resolve_alert_type(db, effective_tid, type)
        if severity is not None:
            alert.severity = parse_alert_severity(severity)
        if obra_id is not None:
            obra = Repository.obras.obter_por_id(db, int(obra_id), tenant_id=effective_tid)
            if not obra:
                raise ValueError("obra_id inválido para este tenant.")
            alert.obra_id = int(obra_id)
        if title is not None:
            alert.title = (title or "").strip() or default_alert_title(str(alert.type))
        if description is not None:
            normalized = (description or "").strip()
            alert.description = normalized or default_alert_description(
                alert_type=str(alert.type),
                location_detail=location_detail if location_detail is not None else alert.location_detail,
                equipment_name=equipment_name if equipment_name is not None else alert.equipment_name,
            )
        if location_detail is not None:
            alert.location_detail = location_detail
        if equipment_name is not None:
            alert.equipment_name = equipment_name
        if photo_urls is not None:
            alert.photo_urls = photo_urls
        if notified_channels is not None:
            alert.notified_channels = notified_channels
        if resolution_notes is not None:
            alert.resolution_notes = resolution_notes
        if new_status is not None:
            alert.status = new_status
            if new_status in {AlertStatus.RESOLVIDO, AlertStatus.CANCELADO}:
                alert.resolved_by = actor_user_id
                alert.resolved_at = datetime.utcnow()
            else:
                alert.resolved_by = None
                alert.resolved_at = None

        db.commit()
        db.refresh(alert)
        return {"ok": True, "alerta": to_dict(alert)}


def marcar_alerta_lido(
    tenant_id: int,
    actor_user_id: int,
    actor_level: str,
    alert_id: str | None,
    alert_code: str | None,
) -> dict:
    assert_permission(actor_level, "read", "alerts")
    with SessionLocal() as db:
        effective_tid = _resolve_tenant(db, tenant_id)
        alert = _get_alert(db, effective_tid, alert_id, alert_code)
        if not alert:
            return {"ok": False, "message": "Alerta não encontrado."}
        existing = (
            db.query(AlertRead)
            .filter(
                AlertRead.alert_id == alert.id,
                AlertRead.worker_id == actor_user_id,
                AlertRead.tenant_id == effective_tid,
            )
            .first()
        )
        if not existing:
            existing = AlertRead(alert_id=alert.id, worker_id=actor_user_id, tenant_id=effective_tid)
            db.add(existing)
        db.commit()
        db.refresh(alert)
        db.refresh(existing)
        return {"ok": True, "alerta": to_dict(alert), "leitura": to_dict(existing)}


def marcar_alerta_nao_lido(
    tenant_id: int,
    actor_user_id: int,
    actor_level: str,
    alert_id: str | None,
    alert_code: str | None,
) -> dict:
    assert_permission(actor_level, "read", "alerts")
    with SessionLocal() as db:
        effective_tid = _resolve_tenant(db, tenant_id)
        alert = _get_alert(db, effective_tid, alert_id, alert_code)
        if not alert:
            return {"ok": False, "message": "Alerta não encontrado."}
        existing = (
            db.query(AlertRead)
            .filter(
                AlertRead.alert_id == alert.id,
                AlertRead.worker_id == actor_user_id,
                AlertRead.tenant_id == effective_tid,
            )
            .first()
        )
        if not existing:
            return {"ok": True, "message": "Alerta já estava como não lido.", "alerta": to_dict(alert)}
        db.delete(existing)
        db.commit()
        db.refresh(alert)
        return {"ok": True, "alerta": to_dict(alert)}


def deletar_alerta(
    tenant_id: int,
    actor_user_id: int,
    actor_level: str,
    alert_id: str | None,
    alert_code: str | None,
) -> dict:
    assert_permission(actor_level, "delete", "alerts")
    with SessionLocal() as db:
        effective_tid = _resolve_tenant(db, tenant_id)
        alert = _get_alert(db, effective_tid, alert_id, alert_code)
        if not alert:
            return {"ok": False, "message": "Alerta não encontrado."}
        deleted_code = alert.code
        db.delete(alert)
        db.commit()
        return {"ok": True, "message": "Alerta removido com sucesso.", "alert_code": deleted_code}
