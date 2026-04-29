from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID
import unicodedata

from flask import Blueprint, g, jsonify, request
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError

from backend.api.routes.auth import require_auth
from backend.db.models import Alert, AlertRead, AlertSeverity, AlertStatus, AlertTypeAlias, NivelAcesso, Usuario
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


def _build_user_name_map(db, user_ids: set[int | None]) -> dict[int, str]:
    ids = {item for item in user_ids if item is not None}
    if not ids:
        return {}
    users = db.query(Usuario.id, Usuario.nome).filter(Usuario.id.in_(ids)).all()
    return {user_id: nome for user_id, nome in users}


def _serialize_alert_summary(alert: Alert, user_names: dict[int, str]):
    return {
        "id": _to_json_value(alert.id),
        "code": alert.code,
        "type": _to_json_value(alert.type),
        "severity": _to_json_value(alert.severity),
        "title": alert.title,
        "status": _to_json_value(alert.status),
        "is_read": bool(alert.is_read),
        "reported_at": _to_json_value(alert.created_at),
        "created_at": _to_json_value(alert.created_at),
        "location_detail": alert.location_detail,
        "reported_by": alert.reported_by,
        "reported_by_nome": user_names.get(alert.reported_by),
    }


def _serialize_alert_detail(alert: Alert, user_names: dict[int, str]):
    payload = _serialize_alert_summary(alert, user_names)
    payload.update(
        {
            "description": alert.description,
            "equipment_name": alert.equipment_name,
            "photo_urls": alert.photo_urls,
            "priority_score": alert.priority_score,
            "resolution_notes": alert.resolution_notes,
            "resolved_by": alert.resolved_by,
            "resolved_by_nome": user_names.get(alert.resolved_by),
            "resolved_at": _to_json_value(alert.resolved_at),
            "read_by": alert.read_by,
            "read_by_nome": user_names.get(alert.read_by),
            "read_at": _to_json_value(alert.read_at),
            "updated_at": _to_json_value(alert.updated_at),
        }
    )
    return payload


def _serialize_tipo_alerta_simple(item: AlertTypeAlias):
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


def _resolve_alert_type(db, value: str) -> str:
    normalized = _normalize_text((value or "").replace("_", " "))
    if not normalized:
        raise ValueError("Campo obrigatório: type")

    alias = (
        db.query(AlertTypeAlias)
        .filter(AlertTypeAlias.normalized_alias == normalized)
        .filter(AlertTypeAlias.ativo.is_(True))
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
        user_ids = {item.reported_by for item in items}
        user_names = _build_user_name_map(db, user_ids)
        return jsonify({"ok": True, "total": len(items), "alertas": [_serialize_alert_summary(item, user_names) for item in items]})


@router.post("")
@require_auth
def criar_alerta():
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
            type_value = _resolve_alert_type(db, data["type"])
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
            created_at=reported_at,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        user_names = _build_user_name_map(db, {alert.reported_by, alert.resolved_by, alert.read_by})
        return jsonify({"ok": True, "alerta": _serialize_alert_detail(alert, user_names)}), 201


@router.get("/<uuid:alert_id>")
@require_auth
def obter_alerta(alert_id):
    with SessionLocal() as db:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return _json_error("Alerta não encontrado.", 404)
        user_names = _build_user_name_map(db, {alert.reported_by, alert.resolved_by, alert.read_by})
        return jsonify({"ok": True, "alerta": _serialize_alert_detail(alert, user_names)})


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
        user_names = _build_user_name_map(db, {alert.reported_by, alert.resolved_by, alert.read_by})
        return jsonify({"ok": True, "alerta": _serialize_alert_detail(alert, user_names)})


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
        user_names = _build_user_name_map(db, {alert.reported_by, alert.resolved_by, alert.read_by, read.worker_id})
        leitura_payload = _to_dict(read)
        leitura_payload["worker_nome"] = user_names.get(read.worker_id)
        return jsonify({"ok": True, "alerta": _serialize_alert_detail(alert, user_names), "leitura": leitura_payload})


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
            user_names = _build_user_name_map(db, {alert.reported_by, alert.resolved_by, alert.read_by})
            return jsonify({"ok": True, "message": "Alerta já estava como não lido para este usuário.", "alerta": _serialize_alert_detail(alert, user_names)})

        db.delete(read)
        _sync_alert_read_flags(db, alert)

        db.commit()
        db.refresh(alert)
        user_names = _build_user_name_map(db, {alert.reported_by, alert.resolved_by, alert.read_by})
        return jsonify({"ok": True, "alerta": _serialize_alert_detail(alert, user_names)})


@router.get("/codigo/<string:code>")
@require_auth
def obter_alerta_por_codigo(code: str):
    with SessionLocal() as db:
        alert = db.query(Alert).filter(Alert.code == code.upper()).first()
        if not alert:
            return _json_error("Alerta não encontrado.", 404)
        user_names = _build_user_name_map(db, {alert.reported_by, alert.resolved_by, alert.read_by})
        return jsonify({"ok": True, "alerta": _serialize_alert_detail(alert, user_names)})


@router.delete("/<uuid:alert_id>")
@require_auth
def deletar_alerta(alert_id):
    if not _is_admin_or_gerente():
        return _json_error("Apenas administrador/gerente pode remover alertas.", 403)

    with SessionLocal() as db:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            return _json_error("Alerta não encontrado.", 404)

        db.delete(alert)
        db.commit()
        return jsonify({"ok": True, "message": "Alerta removido com sucesso."})


@router.get("/tipos")
@require_auth
def listar_tipos_alerta():
    ativos_apenas = request.args.get("ativos_apenas", "false").lower() in {"1", "true", "yes", "on"}
    with SessionLocal() as db:
        query = db.query(AlertTypeAlias)
        if ativos_apenas:
            query = query.filter(AlertTypeAlias.ativo.is_(True))
        items = query.order_by(AlertTypeAlias.alias.asc()).limit(500).all()
        canonical_types = [
            row[0]
            for row in db.query(AlertTypeAlias.canonical_type)
            .distinct()
            .order_by(AlertTypeAlias.canonical_type.asc())
            .all()
        ]
        return jsonify(
            {
                "ok": True,
                "total": len(items),
                "tipos_alerta": [_to_dict(item) for item in items],
                "tipos_canonicos": canonical_types,
            }
        )


@router.get("/tipos/simples")
@require_auth
def listar_tipos_alerta_simples():
    ativos_apenas = request.args.get("ativos_apenas", "true").lower() in {"1", "true", "yes", "on"}
    with SessionLocal() as db:
        query = db.query(AlertTypeAlias)
        if ativos_apenas:
            query = query.filter(AlertTypeAlias.ativo.is_(True))
        items = query.order_by(AlertTypeAlias.alias.asc()).limit(500).all()
        return jsonify(
            {
                "ok": True,
                "total": len(items),
                "tipos": [_serialize_tipo_alerta_simple(item) for item in items],
            }
        )


@router.post("/tipos/simples")
@require_auth
def criar_tipo_alerta_simples():
    if not _is_admin_or_gerente():
        return _json_error("Apenas administrador/gerente pode cadastrar tipo de alerta.", 403)

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

    data = request.get_json(silent=True) or {}
    with SessionLocal() as db:
        item = db.query(AlertTypeAlias).filter(AlertTypeAlias.id == tipo_id).first()
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

    with SessionLocal() as db:
        item = db.query(AlertTypeAlias).filter(AlertTypeAlias.id == tipo_id).first()
        if not item:
            return _json_error("Tipo de alerta não encontrado.", 404)

        db.delete(item)
        db.commit()
        return jsonify({"ok": True, "message": "Tipo de alerta removido com sucesso."})


@router.get("/tipos/<uuid:tipo_id>")
@require_auth
def obter_tipo_alerta(tipo_id):
    with SessionLocal() as db:
        item = db.query(AlertTypeAlias).filter(AlertTypeAlias.id == tipo_id).first()
        if not item:
            return _json_error("Tipo de alerta não encontrado.", 404)
        return jsonify({"ok": True, "tipo_alerta": _to_dict(item)})


@router.post("/tipos")
@require_auth
def criar_tipo_alerta():
    if not _is_admin_or_gerente():
        return _json_error("Apenas administrador/gerente pode cadastrar tipo de alerta.", 403)

    data = request.get_json(silent=True) or {}
    alias = (data.get("alias") or "").strip()
    if not alias:
        return _json_error("Campo obrigatório: alias")

    try:
        canonical_type = _normalize_alert_type_value((data.get("tipo_canonico") or alias), "tipo_canonico")
    except ValueError as exc:
        return _json_error(str(exc), 422)

    with SessionLocal() as db:
        item = AlertTypeAlias(
            alias=alias,
            normalized_alias=_normalize_text(alias),
            canonical_type=canonical_type,
            descricao=(data.get("descricao") or "").strip() or None,
            ativo=bool(data.get("ativo", True)),
            created_by=g.current_user.id,
            updated_by=g.current_user.id,
        )
        db.add(item)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return _json_error("Já existe um tipo de alerta com este alias.", 409)
        db.refresh(item)
        return jsonify({"ok": True, "tipo_alerta": _to_dict(item)}), 201


@router.patch("/tipos/<uuid:tipo_id>")
@require_auth
def atualizar_tipo_alerta(tipo_id):
    if not _is_admin_or_gerente():
        return _json_error("Apenas administrador/gerente pode atualizar tipo de alerta.", 403)

    data = request.get_json(silent=True) or {}
    with SessionLocal() as db:
        item = db.query(AlertTypeAlias).filter(AlertTypeAlias.id == tipo_id).first()
        if not item:
            return _json_error("Tipo de alerta não encontrado.", 404)

        if "alias" in data:
            alias = (data.get("alias") or "").strip()
            if not alias:
                return _json_error("alias não pode ser vazio.", 422)
            item.alias = alias
            item.normalized_alias = _normalize_text(alias)

        if "tipo_canonico" in data:
            try:
                item.canonical_type = _normalize_alert_type_value(data.get("tipo_canonico"), "tipo_canonico")
            except ValueError as exc:
                return _json_error(str(exc), 422)

        if "descricao" in data:
            item.descricao = (data.get("descricao") or "").strip() or None

        if "ativo" in data:
            item.ativo = bool(data.get("ativo"))

        item.updated_by = g.current_user.id

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return _json_error("Não foi possível atualizar: alias já existe.", 409)

        db.refresh(item)
        return jsonify({"ok": True, "tipo_alerta": _to_dict(item)})


@router.delete("/tipos/<uuid:tipo_id>")
@require_auth
def deletar_tipo_alerta(tipo_id):
    if not _is_admin_or_gerente():
        return _json_error("Apenas administrador/gerente pode remover tipo de alerta.", 403)

    with SessionLocal() as db:
        item = db.query(AlertTypeAlias).filter(AlertTypeAlias.id == tipo_id).first()
        if not item:
            return _json_error("Tipo de alerta não encontrado.", 404)

        db.delete(item)
        db.commit()
        return jsonify({"ok": True, "message": "Tipo de alerta removido com sucesso."})
