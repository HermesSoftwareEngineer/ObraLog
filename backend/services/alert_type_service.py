"""Serviço de tipos de alerta operacional."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from backend.agents.tools.database.common import assert_permission, normalize_text, to_dict
from backend.db.models import AlertTypeAlias
from backend.db.repository import Repository
from backend.db.session import SessionLocal


def _parse_canonical_type(value: str | None) -> str:
    normalized = normalize_text((value or "").replace("_", " "))
    if not normalized:
        raise ValueError("tipo_canonico é obrigatório.")
    return normalized.replace(" ", "_")


def _alias_to_dict(item: AlertTypeAlias) -> dict:
    payload = to_dict(item)
    payload["tipo_canonico"] = payload.pop("canonical_type", None)
    return payload


def _get_alias(db, tenant_id: int, tipo_id: str | None, alias: str | None) -> AlertTypeAlias | None:
    if tipo_id:
        return (
            db.query(AlertTypeAlias)
            .filter(AlertTypeAlias.id == uuid.UUID(str(tipo_id)), AlertTypeAlias.tenant_id == tenant_id)
            .first()
        )
    if alias:
        normalized = normalize_text(alias)
        return (
            db.query(AlertTypeAlias)
            .filter(AlertTypeAlias.normalized_alias == normalized, AlertTypeAlias.tenant_id == tenant_id)
            .first()
        )
    raise ValueError("Informe tipo_id ou alias para identificar o tipo de alerta.")


def _resolve_tenant(db, tenant_id: int) -> int:
    if tenant_id is not None:
        return int(tenant_id)
    return int(Repository.tenants.get_default(db).id)


def listar_tipos_alerta(tenant_id: int, actor_level: str, ativos_apenas: bool = False) -> dict:
    assert_permission(actor_level, "read", "alert_types")
    with SessionLocal() as db:
        effective_tid = _resolve_tenant(db, tenant_id)
        query = db.query(AlertTypeAlias).filter(AlertTypeAlias.tenant_id == effective_tid)
        if ativos_apenas:
            query = query.filter(AlertTypeAlias.ativo.is_(True))
        items = query.order_by(AlertTypeAlias.alias.asc()).all()
        tipos = [_alias_to_dict(i) for i in items]
        canonical_types = [
            row[0] for row in
            db.query(AlertTypeAlias.canonical_type)
            .filter(AlertTypeAlias.tenant_id == effective_tid)
            .distinct()
            .order_by(AlertTypeAlias.canonical_type.asc())
            .all()
        ]
        return {"ok": True, "total": len(tipos), "tipos_alerta": tipos, "tipos_canonicos": canonical_types}


def obter_tipo_alerta(
    tenant_id: int,
    actor_level: str,
    tipo_id: str | None,
    alias: str | None,
) -> dict:
    assert_permission(actor_level, "read", "alert_types")
    with SessionLocal() as db:
        effective_tid = _resolve_tenant(db, tenant_id)
        item = _get_alias(db, effective_tid, tipo_id, alias)
        if not item:
            return {"ok": False, "message": "Tipo de alerta não encontrado."}
        return {"ok": True, "tipo_alerta": _alias_to_dict(item)}


def criar_tipo_alerta(
    tenant_id: int,
    actor_user_id: int,
    actor_level: str,
    alias: str,
    tipo_canonico: str,
    descricao: str | None = None,
    ativo: bool = True,
) -> dict:
    assert_permission(actor_level, "create", "alert_types")
    normalized_alias = normalize_text(alias or "")
    if not normalized_alias:
        raise ValueError("alias é obrigatório para criar tipo de alerta.")
    canonical_type = _parse_canonical_type(tipo_canonico)
    with SessionLocal() as db:
        effective_tid = _resolve_tenant(db, tenant_id)
        item = AlertTypeAlias(
            tenant_id=effective_tid,
            alias=str(alias).strip(),
            normalized_alias=normalized_alias,
            canonical_type=canonical_type,
            descricao=(descricao or "").strip() or None,
            ativo=bool(ativo),
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        db.add(item)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError("Já existe um tipo de alerta com este alias.") from exc
        db.refresh(item)
        return {"ok": True, "tipo_alerta": _alias_to_dict(item)}


def atualizar_tipo_alerta(
    tenant_id: int,
    actor_user_id: int,
    actor_level: str,
    tipo_id: str | None,
    alias: str | None,
    *,
    novo_alias: str | None = None,
    tipo_canonico: str | None = None,
    descricao: str | None = None,
    ativo: bool | None = None,
) -> dict:
    assert_permission(actor_level, "update", "alert_types")
    with SessionLocal() as db:
        effective_tid = _resolve_tenant(db, tenant_id)
        item = _get_alias(db, effective_tid, tipo_id, alias)
        if not item:
            return {"ok": False, "message": "Tipo de alerta não encontrado."}
        if novo_alias is not None:
            normalized_new = normalize_text(novo_alias)
            if not normalized_new:
                raise ValueError("novo_alias não pode ser vazio.")
            item.alias = str(novo_alias).strip()
            item.normalized_alias = normalized_new
        if tipo_canonico is not None:
            item.canonical_type = _parse_canonical_type(tipo_canonico)
        if descricao is not None:
            item.descricao = (descricao or "").strip() or None
        if ativo is not None:
            item.ativo = bool(ativo)
        item.updated_by = actor_user_id
        item.updated_at = datetime.utcnow()
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError("Não foi possível atualizar: alias já existe.") from exc
        db.refresh(item)
        return {"ok": True, "tipo_alerta": _alias_to_dict(item)}


def deletar_tipo_alerta(
    tenant_id: int,
    actor_level: str,
    tipo_id: str | None,
    alias: str | None,
) -> dict:
    assert_permission(actor_level, "delete", "alert_types")
    with SessionLocal() as db:
        effective_tid = _resolve_tenant(db, tenant_id)
        item = _get_alias(db, effective_tid, tipo_id, alias)
        if not item:
            return {"ok": False, "message": "Tipo de alerta não encontrado."}
        removed_alias = item.alias
        db.delete(item)
        db.commit()
        return {"ok": True, "message": "Tipo de alerta removido com sucesso.", "alias": removed_alias}
