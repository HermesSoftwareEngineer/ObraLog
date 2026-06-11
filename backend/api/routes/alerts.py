from __future__ import annotations
print("[BOOT] alerts.py: módulo carregando...", flush=True)

from datetime import datetime, timezone
from uuid import UUID
import unicodedata

from flask import Blueprint, g, jsonify, request
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError

from backend.api.routes.auth import require_auth
from backend.db.models import Alert, AlertRead, AlertSeverity, AlertStatus, AlertTypeAlias, NivelAcesso, Obra, Usuario
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


def _build_user_name_map(db, user_ids: set[int | None]) -> dict[int, str]:
    ids = {item for item in user_ids if item is not None}
    if not ids:
        return {}
    users = db.query(Usuario.id, Usuario.nome).filter(Usuario.id.in_(ids)).all()
    return {user_id: nome for user_id, nome in users}


def _build_read_ids(db, user_id: int, tenant_id: int, alert_ids: set | None = None) -> set:
    """Retorna o conjunto de alert_ids que o usuário já leu."""
    query = (
        db.query(AlertRead.alert_id)
        .filter(AlertRead.worker_id == user_id, AlertRead.tenant_id == tenant_id)
    )
    if alert_ids is not None:
        query = query.filter(AlertRead.alert_id.in_(alert_ids))
    return {row[0] for row in query.all()}


def _serialize_alert_summary(alert: Alert, user_names: dict[int, str], is_read: bool) -> dict:
    return {
        "id": _to_json_value(alert.id),
        "code": alert.code,
        "type": _to_json_value(alert.type),
        "severity": _to_json_value(alert.severity),
        "obra_id": alert.obra_id,
        "title": alert.title,
        "description": alert.description,
        "status": _to_json_value(alert.status),
        "is_read": is_read,
        "reported_at": _to_json_value(alert.created_at),
        "created_at": _to_json_value(alert.created_at),
        "location_detail": alert.location_detail,
        "reported_by": alert.reported_by,
        "reported_by_nome": user_names.get(alert.reported_by),
    }


def _serialize_alert_detail(alert: Alert, user_names: dict[int, str], is_read: bool) -> dict:
    payload = _serialize_alert_summary(alert, user_names, is_read)
    payload.update(
        {
            "equipment_name": alert.equipment_name,
            "photo_urls": alert.photo_urls,
            "resolution_notes": alert.resolution_notes,
            "resolved_by": alert.resolved_by,
            "resolved_by_nome": user_names.get(alert.resolved_by),
            "resolved_at": _to_json_value(alert.resolved_at),
            "updated_at": _to_json_value(alert.updated_at),
        }
    )
    return payload


def _serialize_tipo_alerta_simple(item: AlertTypeAlias) -> dict:
    return {
        "id": _to_json_value(item.id),
        "nome": item.alias,
        "tipo_canonico": _to_json_value(item.canonical_type),
        "ativo": bool(item.ativo),
    }


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.strip().lower().split())


def _normalize_alert_type_value(value: str | None, field_name: str = "tipo_canonico") -> str:
    normalized = _normalize_text((value or "").replace("_", " "))
    if not normalized:
        raise ValueError(f"Campo obrigatório: {field_name}")
    return normalized.replace(" ", "_")


def _resolve_alert_type(db, value: str, tenant_id: int) -> str:
    normalized = _normalize_text((value or "").replace("_", " "))
    if not normalized:
        raise ValueError("Campo obrigatório: type")

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

    return normalized.replace(" ", "_")


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
    alert_type: str,
    location_detail: str | None = None,
    equipment_name: str | None = None,
) -> str:
    base_by_type = {
        "maquina_quebrada": "Máquina/equipamento com falha operacional",
        "acidente": "Ocorrência de acidente em campo",
        "falta_material": "Ocorrência de falta de material",
        "risco_seguranca": "Ocorrência de risco de segurança",
        "outro": "Ocorrência operacional reportada",
    }
    parts = [base_by_type.get(str(alert_type), "Ocorrência operacional reportada")]
    if location_detail:
        parts.append(f"Local: {location_detail}")
    if equipment_name:
        parts.append(f"Equipamento: {equipment_name}")
    return ". ".join(parts)


def _is_admin_or_gerente() -> bool:
    nivel = g.current_user.nivel_acesso.value if hasattr(g.current_user.nivel_acesso, "value") else str(g.current_user.nivel_acesso)
    return nivel in {NivelAcesso.ADMINISTRADOR.value, NivelAcesso.GERENTE.value}


def _is_agent_source(value: str | None) -> bool:
    source = (value or "").strip().lower()
    return source.startswith("agent") or source in {"telegram_agent", "ia"}


def _parse_reported_at(value: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Campo obrigatório: reported_at")
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("reported_at inválido. Use formato ISO8601, por exemplo: 2026-04-29T14:30:00-03:00") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _generate_alert_code(db, tenant_id: int) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"ALT-{year}-"
    count = (
        db.query(func.count(Alert.id))
        .filter(Alert.code.like(f"{prefix}%"), Alert.tenant_id == tenant_id)
        .scalar()
    ) or 0
    return f"{prefix}{count + 1:04d}"


# ---------------------------------------------------------------------------
# Alertas
# ---------------------------------------------------------------------------

@router.get("")
@require_auth
def listar_alertas():
    tenant_id = getattr(g, "tenant_id", None)
    user_id = g.current_user.id
    with SessionLocal() as db:
        query = db.query(Alert).filter(Alert.tenant_id == tenant_id)

        status = request.args.get("status")
        severity = request.args.get("severity")
        obra_id = request.args.get("obra_id")
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

        if obra_id not in (None, ""):
            try:
                query = query.filter(Alert.obra_id == int(obra_id))
            except (ValueError, TypeError):
                return _json_error("obra_id inválido. Use inteiro.", 422)

        if apenas_nao_lidos:
            read_subq = (
                db.query(AlertRead.alert_id)
                .filter(AlertRead.worker_id == user_id, AlertRead.tenant_id == tenant_id)
            )
            query = query.filter(Alert.id.notin_(read_subq))

        items = query.order_by(Alert.created_at.desc()).limit(200).all()

        read_ids: set = set()
        if items:
            item_ids = {item.id for item in items}
            read_ids = _build_read_ids(db, user_id, tenant_id, alert_ids=item_ids)

        user_ids = {item.reported_by for item in items}
        user_names = _build_user_name_map(db, user_ids)

        return jsonify({
            "ok": True,
            "total": len(items),
            "alertas": [_serialize_alert_summary(item, user_names, item.id in read_ids) for item in items],
        })


@router.post("")
@require_auth
def criar_alerta():
    tenant_id = getattr(g, "tenant_id", None)
    data = request.get_json(silent=True) or {}
    source = data.get("source")
    is_agent_request = _is_agent_source(source)
    try:
        title = data["title"]
        severity_value = _parse_alert_severity(data["severity"])
    except KeyError as exc:
        return _json_error(f"Campo obrigatório ausente: {exc.args[0]}")
    except ValueError as exc:
        return _json_error(str(exc), 422)

    reported_at_raw = data.get("reported_at")
    if reported_at_raw:
        try:
            reported_at = _parse_reported_at(reported_at_raw)
        except ValueError as exc:
            return _json_error(str(exc), 422)
    elif is_agent_request:
        reported_at = datetime.now(timezone.utc)
    else:
        return _json_error("Campo obrigatório: reported_at", 422)

    with SessionLocal() as db:
        try:
            type_value = _resolve_alert_type(db, data["type"], tenant_id)
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

        obra_id = data.get("obra_id")
        if obra_id not in (None, ""):
            try:
                obra_id = int(obra_id)
            except (ValueError, TypeError):
                return _json_error("obra_id inválido. Use inteiro.", 422)
            obra = db.query(Obra).filter(Obra.id == obra_id, Obra.tenant_id == tenant_id).first()
            if not obra:
                return _json_error("Obra não encontrada para este tenant.", 404)
        else:
            obra_id = None

        alert = Alert(
            tenant_id=tenant_id,
            code=_generate_alert_code(db, tenant_id),
            type=type_value,
            severity=severity_value,
            reported_by=g.current_user.id,
            obra_id=obra_id,
            telegram_message_id=data.get("telegram_message_id"),
            title=title,
            description=description,
            raw_text=data.get("raw_text"),
            location_detail=data.get("location_detail"),
            equipment_name=data.get("equipment_name"),
            photo_urls=data.get("photo_urls"),
            status=AlertStatus.ABERTO,
            notified_channels=data.get("notified_channels"),
            created_at=reported_at,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        user_names = _build_user_name_map(db, {alert.reported_by, alert.resolved_by})
        return jsonify({"ok": True, "alerta": _serialize_alert_detail(alert, user_names, is_read=False)}), 201


@router.get("/<uuid:alert_id>")
@require_auth
def obter_alerta(alert_id):
    tenant_id = getattr(g, "tenant_id", None)
    user_id = g.current_user.id
    with SessionLocal() as db:
        alert = db.query(Alert).filter(Alert.id == alert_id, Alert.tenant_id == tenant_id).first()
        if not alert:
            return _json_error("Alerta não encontrado.", 404)
        is_read = bool(
            db.query(AlertRead.id)
            .filter(AlertRead.alert_id == alert_id, AlertRead.worker_id == user_id)
            .first()
        )
        user_names = _build_user_name_map(db, {alert.reported_by, alert.resolved_by})
        return jsonify({"ok": True, "alerta": _serialize_alert_detail(alert, user_names, is_read)})


@router.get("/codigo/<string:code>")
@require_auth
def obter_alerta_por_codigo(code: str):
    tenant_id = getattr(g, "tenant_id", None)
    user_id = g.current_user.id
    with SessionLocal() as db:
        alert = db.query(Alert).filter(Alert.code == code.upper(), Alert.tenant_id == tenant_id).first()
        if not alert:
            return _json_error("Alerta não encontrado.", 404)
        is_read = bool(
            db.query(AlertRead.id)
            .filter(AlertRead.alert_id == alert.id, AlertRead.worker_id == user_id)
            .first()
        )
        user_names = _build_user_name_map(db, {alert.reported_by, alert.resolved_by})
        return jsonify({"ok": True, "alerta": _serialize_alert_detail(alert, user_names, is_read)})


_UPDATABLE_FIELDS = {"status", "obra_id", "resolution_notes", "title", "type", "severity",
                     "description", "location_detail", "equipment_name"}


@router.patch("/<uuid:alert_id>/status")
@require_auth
def atualizar_alerta(alert_id):
    if not _is_admin_or_gerente():
        return _json_error("Apenas administrador/gerente pode atualizar alertas.", 403)

    data = request.get_json(silent=True) or {}
    if not any(key in data for key in _UPDATABLE_FIELDS):
        return _json_error("Informe ao menos um campo para atualizar.", 422)

    tenant_id = getattr(g, "tenant_id", None)
    user_id = g.current_user.id

    with SessionLocal() as db:
        alert = db.query(Alert).filter(Alert.id == alert_id, Alert.tenant_id == tenant_id).first()
        if not alert:
            return _json_error("Alerta não encontrado.", 404)

        if "title" in data:
            title = (data["title"] or "").strip()
            if not title:
                return _json_error("title não pode ser vazio.", 422)
            alert.title = title

        if "type" in data:
            try:
                alert.type = _resolve_alert_type(db, data["type"], tenant_id)
            except ValueError as exc:
                return _json_error(str(exc), 422)

        if "severity" in data:
            try:
                alert.severity = _parse_alert_severity(data["severity"])
            except ValueError as exc:
                return _json_error(str(exc), 422)

        if "description" in data:
            alert.description = (data["description"] or "").strip() or alert.description

        if "location_detail" in data:
            alert.location_detail = data.get("location_detail")

        if "equipment_name" in data:
            alert.equipment_name = data.get("equipment_name")

        if "resolution_notes" in data:
            alert.resolution_notes = data.get("resolution_notes")

        if "obra_id" in data:
            obra_id = data.get("obra_id")
            if obra_id in (None, ""):
                alert.obra_id = None
            else:
                try:
                    obra_id = int(obra_id)
                except (ValueError, TypeError):
                    return _json_error("obra_id inválido. Use inteiro.", 422)
                obra = db.query(Obra).filter(Obra.id == obra_id, Obra.tenant_id == tenant_id).first()
                if not obra:
                    return _json_error("Obra não encontrada para este tenant.", 404)
                alert.obra_id = obra_id

        if "status" in data:
            try:
                new_status = _parse_alert_status(data["status"])
            except ValueError as exc:
                return _json_error(str(exc), 422)
            alert.status = new_status
            if new_status in {AlertStatus.RESOLVIDO, AlertStatus.CANCELADO}:
                alert.resolved_by = user_id
                alert.resolved_at = datetime.now(timezone.utc)
            else:
                alert.resolved_by = None
                alert.resolved_at = None

        db.commit()
        db.refresh(alert)
        is_read = bool(
            db.query(AlertRead.id)
            .filter(AlertRead.alert_id == alert.id, AlertRead.worker_id == user_id)
            .first()
        )
        user_names = _build_user_name_map(db, {alert.reported_by, alert.resolved_by})
        return jsonify({"ok": True, "alerta": _serialize_alert_detail(alert, user_names, is_read)})


@router.post("/<uuid:alert_id>/read")
@require_auth
def marcar_como_lido(alert_id):
    tenant_id = getattr(g, "tenant_id", None)
    user_id = g.current_user.id
    with SessionLocal() as db:
        alert = db.query(Alert).filter(Alert.id == alert_id, Alert.tenant_id == tenant_id).first()
        if not alert:
            return _json_error("Alerta não encontrado.", 404)

        read = (
            db.query(AlertRead)
            .filter(AlertRead.alert_id == alert_id, AlertRead.worker_id == user_id)
            .first()
        )
        if not read:
            read = AlertRead(alert_id=alert_id, worker_id=user_id, tenant_id=tenant_id)
            db.add(read)
            db.commit()
            db.refresh(read)

        user_names = _build_user_name_map(db, {alert.reported_by, alert.resolved_by})
        return jsonify({"ok": True, "alerta": _serialize_alert_detail(alert, user_names, is_read=True)})


@router.post("/<uuid:alert_id>/unread")
@require_auth
def marcar_como_nao_lido(alert_id):
    tenant_id = getattr(g, "tenant_id", None)
    user_id = g.current_user.id
    with SessionLocal() as db:
        alert = db.query(Alert).filter(Alert.id == alert_id, Alert.tenant_id == tenant_id).first()
        if not alert:
            return _json_error("Alerta não encontrado.", 404)

        read = (
            db.query(AlertRead)
            .filter(AlertRead.alert_id == alert_id, AlertRead.worker_id == user_id)
            .first()
        )
        user_names = _build_user_name_map(db, {alert.reported_by, alert.resolved_by})
        if not read:
            return jsonify({"ok": True, "alerta": _serialize_alert_detail(alert, user_names, is_read=False)})

        db.delete(read)
        db.commit()
        return jsonify({"ok": True, "alerta": _serialize_alert_detail(alert, user_names, is_read=False)})


@router.delete("/<uuid:alert_id>")
@require_auth
def deletar_alerta(alert_id):
    if not _is_admin_or_gerente():
        return _json_error("Apenas administrador/gerente pode remover alertas.", 403)

    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        alert = db.query(Alert).filter(Alert.id == alert_id, Alert.tenant_id == tenant_id).first()
        if not alert:
            return _json_error("Alerta não encontrado.", 404)

        db.delete(alert)
        db.commit()
        return jsonify({"ok": True, "message": "Alerta removido com sucesso."})


# ---------------------------------------------------------------------------
# Tipos de alerta
# ---------------------------------------------------------------------------

@router.get("/tipos/simples")
@require_auth
def listar_tipos_alerta_simples():
    tenant_id = getattr(g, "tenant_id", None)
    ativos_apenas = request.args.get("ativos_apenas", "true").lower() in {"1", "true", "yes", "on"}
    with SessionLocal() as db:
        query = db.query(AlertTypeAlias).filter(AlertTypeAlias.tenant_id == tenant_id)
        if ativos_apenas:
            query = query.filter(AlertTypeAlias.ativo.is_(True))
        items = query.order_by(AlertTypeAlias.alias.asc()).limit(500).all()
        return jsonify({"ok": True, "total": len(items), "tipos": [_serialize_tipo_alerta_simple(item) for item in items]})


@router.post("/tipos/simples")
@require_auth
def criar_tipo_alerta_simples():
    if not _is_admin_or_gerente():
        return _json_error("Apenas administrador/gerente pode cadastrar tipo de alerta.", 403)

    tenant_id = getattr(g, "tenant_id", None)
    data = request.get_json(silent=True) or {}
    nome = (data.get("nome") or "").strip()
    if not nome:
        return _json_error("Campo obrigatório: nome", 422)

    try:
        canonical_type = _normalize_alert_type_value((data.get("tipo_canonico") or nome), "tipo_canonico")
    except ValueError as exc:
        return _json_error(str(exc), 422)

    with SessionLocal() as db:
        item = AlertTypeAlias(
            alias=nome,
            normalized_alias=_normalize_text(nome),
            canonical_type=canonical_type,
            ativo=bool(data.get("ativo", True)),
            tenant_id=tenant_id,
            created_by=g.current_user.id,
            updated_by=g.current_user.id,
        )
        db.add(item)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return _json_error("Já existe um tipo de alerta com este nome.", 409)

        db.refresh(item)
        return jsonify({"ok": True, "tipo": _serialize_tipo_alerta_simple(item)}), 201


@router.patch("/tipos/simples/<uuid:tipo_id>")
@require_auth
def atualizar_tipo_alerta_simples(tipo_id):
    if not _is_admin_or_gerente():
        return _json_error("Apenas administrador/gerente pode atualizar tipo de alerta.", 403)

    tenant_id = getattr(g, "tenant_id", None)
    data = request.get_json(silent=True) or {}
    with SessionLocal() as db:
        item = db.query(AlertTypeAlias).filter(
            AlertTypeAlias.id == tipo_id, AlertTypeAlias.tenant_id == tenant_id
        ).first()
        if not item:
            return _json_error("Tipo de alerta não encontrado.", 404)

        if "nome" in data:
            nome = (data.get("nome") or "").strip()
            if not nome:
                return _json_error("nome não pode ser vazio.", 422)
            item.alias = nome
            item.normalized_alias = _normalize_text(nome)

        if "tipo_canonico" in data:
            try:
                item.canonical_type = _normalize_alert_type_value(data.get("tipo_canonico"), "tipo_canonico")
            except ValueError as exc:
                return _json_error(str(exc), 422)

        if "ativo" in data:
            item.ativo = bool(data.get("ativo"))

        item.updated_by = g.current_user.id

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return _json_error("Não foi possível atualizar: nome já existe.", 409)

        db.refresh(item)
        return jsonify({"ok": True, "tipo": _serialize_tipo_alerta_simple(item)})


@router.delete("/tipos/simples/<uuid:tipo_id>")
@require_auth
def deletar_tipo_alerta_simples(tipo_id):
    if not _is_admin_or_gerente():
        return _json_error("Apenas administrador/gerente pode remover tipo de alerta.", 403)

    tenant_id = getattr(g, "tenant_id", None)
    with SessionLocal() as db:
        item = db.query(AlertTypeAlias).filter(
            AlertTypeAlias.id == tipo_id, AlertTypeAlias.tenant_id == tenant_id
        ).first()
        if not item:
            return _json_error("Tipo de alerta não encontrado.", 404)

        db.delete(item)
        db.commit()
        return jsonify({"ok": True, "message": "Tipo de alerta removido com sucesso."})
