from datetime import datetime
import uuid

from langchain_core.tools import tool

from backend.db.models import Alert, AlertRead, AlertStatus, AlertTypeAlias
from backend.db.repository import Repository
from backend.db.session import SessionLocal

from .common import (
    assert_permission,
    default_alert_description,
    default_alert_title,
    generate_alert_code,
    parse_alert_severity,
    parse_alert_status,
    parse_alert_type,
    sync_alert_read_flags,
    to_dict,
    normalize_text,
)


def build_alerts_tools(actor_user_id: int, actor_level: str, tenant_id: int | None = None) -> list:
    def _effective_tenant_id(db) -> int:
        if tenant_id is not None:
            return int(tenant_id)
        return int(Repository.tenants.get_default(db).id)

    def _get_alert(db, alert_id: str | None = None, alert_code: str | None = None):
        effective_tenant_id = _effective_tenant_id(db)
        if alert_id:
            alert_uuid = uuid.UUID(alert_id)
            query = db.query(Alert).filter(Alert.id == alert_uuid, Alert.tenant_id == effective_tenant_id)
            return query.first()
        if alert_code:
            query = db.query(Alert).filter(Alert.code == str(alert_code).strip(), Alert.tenant_id == effective_tenant_id)
            return query.first()
        raise ValueError("Informe alert_id ou alert_code para identificar o alerta.")

    def _resolve_alert_type(db, value: str):
        normalized = normalize_text((value or "").replace("_", " "))
        if not normalized:
            raise ValueError("type é obrigatório para criar alerta.")

        alias = (
            db.query(AlertTypeAlias)
            .filter(AlertTypeAlias.normalized_alias == normalized)
            .filter(AlertTypeAlias.ativo.is_(True))
        )
        if tenant_id is not None:
            alias = alias.filter(AlertTypeAlias.tenant_id == tenant_id)
        alias = alias.first()
        if alias:
            return str(alias.canonical_type)

        return parse_alert_type(value)

    def _resolve_obra_id(db, obra_id_value: int | None, *, effective_tenant_id: int) -> int | None:
        if obra_id_value is None:
            return None
        obra = Repository.obras.obter_por_id(db, int(obra_id_value), tenant_id=effective_tenant_id)
        if not obra:
            raise ValueError("obra_id inválido para este tenant.")
        return int(obra.id)

    @tool
    def criar_alerta(
        type: str,
        description: str | None = None,
        severity: str | None = None,
        title: str | None = None,
        obra_id: int | None = None,
        raw_text: str | None = None,
        location_detail: str | None = None,
        equipment_name: str | None = None,
        photo_urls: list[str] | None = None,
        priority_score: int | None = None,
        telegram_message_id: int | None = None,
        notified_channels: list[str] | None = None,
    ) -> dict:
        """Cria alerta operacional."""
        assert_permission(actor_level, "create", "alerts")
        with SessionLocal() as db:
            effective_tenant_id = _effective_tenant_id(db)
            resolved_obra_id = _resolve_obra_id(db, obra_id, effective_tenant_id=effective_tenant_id)
            alert_type = _resolve_alert_type(db, type)
            alert_severity = parse_alert_severity(severity)
            normalized_description = (description or "").strip()
            used_description_suggestion = not bool(normalized_description)
            if not normalized_description:
                normalized_description = default_alert_description(
                    alert_type=alert_type,
                    location_detail=(location_detail or "").strip() or None,
                    equipment_name=(equipment_name or "").strip() or None,
                )

            alert = Alert(
                tenant_id=effective_tenant_id,
                code=generate_alert_code(db, tenant_id=effective_tenant_id),
                type=alert_type,
                severity=alert_severity,
                reported_by=actor_user_id,
                obra_id=resolved_obra_id,
                telegram_message_id=telegram_message_id,
                title=(title or "").strip() or default_alert_title(alert_type),
                description=normalized_description,
                raw_text=raw_text,
                location_detail=location_detail,
                equipment_name=equipment_name,
                photo_urls=photo_urls,
                status=AlertStatus.ABERTO,
                priority_score=priority_score,
                notified_channels=notified_channels,
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)
            payload = {"ok": True, "alerta": to_dict(alert)}
            if used_description_suggestion:
                payload["description_sugerida"] = normalized_description
            return payload

    @tool
    def obter_alerta(alert_id: str | None = None, alert_code: str | None = None) -> dict:
        """Obtém um alerta por UUID técnico ou código de negócio."""
        assert_permission(actor_level, "read", "alerts")
        with SessionLocal() as db:
            alert = _get_alert(db, alert_id=alert_id, alert_code=alert_code)
            if not alert:
                return {"ok": False, "message": "Alerta não encontrado."}

            effective_tenant_id = _effective_tenant_id(db)
            return {"ok": True, "alerta": to_dict(alert)}

    @tool
    def listar_alertas(
        status: str | None = None,
        severity: str | None = None,
        obra_id: int | None = None,
        apenas_nao_lidos: bool = False,
        limit: int = 50,
    ) -> dict:
        """Lista alertas com filtros de status e severidade."""
        assert_permission(actor_level, "read", "alerts")
        with SessionLocal() as db:
            effective_tenant_id = _effective_tenant_id(db)
            query = db.query(Alert).filter(Alert.tenant_id == effective_tenant_id)
            if status:
                query = query.filter(Alert.status == parse_alert_status(status))
            if severity:
                query = query.filter(Alert.severity == parse_alert_severity(severity))
            if obra_id is not None:
                query = query.filter(Alert.obra_id == int(obra_id))
            if apenas_nao_lidos:
                query = query.filter(Alert.is_read.is_(False))

            items = (
                query.order_by(Alert.created_at.desc())
                .limit(max(1, min(limit, 200)))
                .all()
            )
            if not items:
                return {
                    "ok": True,
                    "total": 0,
                    "alertas": [],
                    "message": "Nenhum alerta encontrado para os filtros informados.",
                    "next_steps": [
                        "consultar outro status",
                        "consultar outra severidade",
                        "listar alertas por periodo no diario",
                        "listar alertas recentes sem filtros",
                    ],
                }
            return {"ok": True, "total": len(items), "alertas": [to_dict(item) for item in items]}

    @tool
    def atualizar_status_alerta(
        alert_id: str | None = None,
        status: str | None = None,
        resolution_notes: str | None = None,
        alert_code: str | None = None,
        type: str | None = None,
        severity: str | None = None,
        obra_id: int | None = None,
        title: str | None = None,
        description: str | None = None,
        location_detail: str | None = None,
        equipment_name: str | None = None,
        photo_urls: list[str] | None = None,
        priority_score: int | None = None,
        notified_channels: list[str] | None = None,
    ) -> dict:
        """Atualiza status e/ou demais campos de um alerta operacional."""
        assert_permission(actor_level, "update", "alerts")

        has_status = status is not None and str(status).strip() != ""
        has_other_updates = any(
            value is not None
            for value in [
                resolution_notes,
                type,
                severity,
                title,
                description,
                location_detail,
                equipment_name,
                photo_urls,
                priority_score,
                notified_channels,
            ]
        )
        if not has_status and not has_other_updates:
            raise ValueError("Informe ao menos um campo para atualizar o alerta.")

        new_status = parse_alert_status(status) if has_status else None

        with SessionLocal() as db:
            alert = _get_alert(db, alert_id=alert_id, alert_code=alert_code)
            if not alert:
                return {"ok": False, "message": "Alerta não encontrado."}

            if type is not None:
                alert.type = _resolve_alert_type(db, type)
            if severity is not None:
                alert.severity = parse_alert_severity(severity)
            if obra_id is not None:
                alert.obra_id = _resolve_obra_id(db, obra_id, effective_tenant_id=effective_tenant_id)
            if title is not None:
                alert.title = (title or "").strip() or default_alert_title(str(alert.type))
            if description is not None:
                normalized_description = (description or "").strip()
                alert.description = normalized_description or default_alert_description(
                    alert_type=str(alert.type),
                    location_detail=(location_detail if location_detail is not None else alert.location_detail),
                    equipment_name=(equipment_name if equipment_name is not None else alert.equipment_name),
                )
            if location_detail is not None:
                alert.location_detail = location_detail
            if equipment_name is not None:
                alert.equipment_name = equipment_name
            if photo_urls is not None:
                alert.photo_urls = photo_urls
            if priority_score is not None:
                alert.priority_score = priority_score
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

    @tool
    def marcar_alerta_como_lido(alert_id: str | None = None, alert_code: str | None = None) -> dict:
        """Marca alerta como lido pelo usuário atual e registra trilha em alert_reads."""
        assert_permission(actor_level, "read", "alerts")

        with SessionLocal() as db:
            effective_tenant_id = _effective_tenant_id(db)
            alert = _get_alert(db, alert_id=alert_id, alert_code=alert_code)
            if not alert:
                return {"ok": False, "message": "Alerta não encontrado."}

            existing = (
                db.query(AlertRead)
                .filter(AlertRead.alert_id == alert.id)
                .filter(AlertRead.worker_id == actor_user_id)
                .filter(AlertRead.tenant_id == effective_tenant_id)
                .first()
            )
            if not existing:
                existing = AlertRead(alert_id=alert.id, worker_id=actor_user_id, tenant_id=effective_tenant_id)
                db.add(existing)

            alert.is_read = True
            alert.read_at = datetime.utcnow()
            alert.read_by = actor_user_id
            db.commit()
            db.refresh(alert)
            db.refresh(existing)
            return {"ok": True, "alerta": to_dict(alert), "leitura": to_dict(existing)}

    @tool
    def marcar_alerta_como_nao_lido(alert_id: str | None = None, alert_code: str | None = None) -> dict:
        """Marca alerta como não lido para o usuário atual."""
        assert_permission(actor_level, "read", "alerts")

        with SessionLocal() as db:
            effective_tenant_id = _effective_tenant_id(db)
            alert = _get_alert(db, alert_id=alert_id, alert_code=alert_code)
            if not alert:
                return {"ok": False, "message": "Alerta não encontrado."}

            existing = (
                db.query(AlertRead)
                .filter(AlertRead.alert_id == alert.id)
                .filter(AlertRead.worker_id == actor_user_id)
                .filter(AlertRead.tenant_id == effective_tenant_id)
                .first()
            )
            if not existing:
                return {"ok": True, "message": "Alerta já estava como não lido para este usuário.", "alerta": to_dict(alert)}

            db.delete(existing)
            sync_alert_read_flags(db, alert)
            db.commit()
            db.refresh(alert)
            return {"ok": True, "alerta": to_dict(alert)}

    @tool
    def deletar_alerta(alert_id: str | None = None, alert_code: str | None = None) -> dict:
        """Remove um alerta por UUID técnico ou código de negócio."""
        assert_permission(actor_level, "delete", "alerts")
        with SessionLocal() as db:
            alert = _get_alert(db, alert_id=alert_id, alert_code=alert_code)
            if not alert:
                return {"ok": False, "message": "Alerta não encontrado."}

            deleted_code = alert.code
            db.delete(alert)
            db.commit()
            return {"ok": True, "message": "Alerta removido com sucesso.", "alert_code": deleted_code}

    return [
        criar_alerta,
        obter_alerta,
        listar_alertas,
        atualizar_status_alerta,
        marcar_alerta_como_lido,
        marcar_alerta_como_nao_lido,
        deletar_alerta,
    ]
