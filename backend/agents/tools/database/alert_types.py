from __future__ import annotations

from datetime import datetime
import uuid

from langchain_core.tools import tool
from sqlalchemy.exc import IntegrityError

from backend.db.models import AlertTypeAlias
from backend.db.repository import Repository
from backend.db.session import SessionLocal

from .common import assert_permission, normalize_text, to_dict


def _parse_canonical_type(value: str | None, field_name: str = "tipo_canonico") -> str:
    normalized = normalize_text((value or "").replace("_", " "))
    if not normalized:
        raise ValueError(f"{field_name} é obrigatório.")
    return normalized.replace(" ", "_")


def _get_alias(db, tipo_id: str | None = None, alias: str | None = None, tenant_id: int | None = None) -> AlertTypeAlias | None:
    if tipo_id:
        query = db.query(AlertTypeAlias).filter(AlertTypeAlias.id == uuid.UUID(str(tipo_id)))
        if tenant_id is not None:
            query = query.filter(AlertTypeAlias.tenant_id == tenant_id)
        return query.first()
    if alias:
        normalized_alias = normalize_text(alias)
        query = db.query(AlertTypeAlias).filter(AlertTypeAlias.normalized_alias == normalized_alias)
        if tenant_id is not None:
            query = query.filter(AlertTypeAlias.tenant_id == tenant_id)
        return query.first()
    raise ValueError("Informe tipo_id ou alias para identificar o tipo de alerta.")


def build_alert_type_tools(actor_user_id: int, actor_level: str, tenant_id: int | None = None) -> list:
    def _effective_tenant_id(db) -> int:
        if tenant_id is not None:
            return int(tenant_id)
        return int(Repository.tenants.get_default(db).id)

    @tool
    def listar_tipos_alerta(ativos_apenas: bool = False) -> dict:
        """Lista tipos de alerta cadastrados para classificar ocorrências em linguagem de negócio."""
        assert_permission(actor_level, "read", "alert_types")
        with SessionLocal() as db:
            query = db.query(AlertTypeAlias)
            if tenant_id is not None:
                query = query.filter(AlertTypeAlias.tenant_id == tenant_id)
            if ativos_apenas:
                query = query.filter(AlertTypeAlias.ativo.is_(True))
            items = query.order_by(AlertTypeAlias.alias.asc()).all()
            tipos = [
                {
                    "id": str(item.id),
                    "alias": item.alias,
                    "tipo_canonico": str(item.canonical_type),
                    "descricao": item.descricao,
                    "ativo": bool(item.ativo),
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                }
                for item in items
            ]
            canonical_query = db.query(AlertTypeAlias.canonical_type)
            if tenant_id is not None:
                canonical_query = canonical_query.filter(AlertTypeAlias.tenant_id == tenant_id)
            canonical_types = [
                row[0]
                for row in canonical_query
                .distinct()
                .order_by(AlertTypeAlias.canonical_type.asc())
                .all()
            ]
            return {
                "ok": True,
                "total": len(tipos),
                "tipos_alerta": tipos,
                "tipos_canonicos": canonical_types,
            }

    @tool
    def obter_tipo_alerta(tipo_id: str | None = None, alias: str | None = None) -> dict:
        """Obtém um tipo de alerta cadastrado por UUID técnico ou alias de negócio."""
        assert_permission(actor_level, "read", "alert_types")
        with SessionLocal() as db:
            item = _get_alias(db, tipo_id=tipo_id, alias=alias, tenant_id=tenant_id)
            if not item:
                return {"ok": False, "message": "Tipo de alerta não encontrado."}
            payload = to_dict(item)
            return {"ok": True, "tipo_alerta": payload}

    @tool
    def criar_tipo_alerta(
        alias: str,
        tipo_canonico: str,
        descricao: str | None = None,
        ativo: bool = True,
    ) -> dict:
        """Cria um alias de tipo de alerta para mapear linguagem de negócio para tipo canônico."""
        assert_permission(actor_level, "create", "alert_types")

        normalized_alias = normalize_text(alias or "")
        if not normalized_alias:
            raise ValueError("alias é obrigatório para criar tipo de alerta.")

        canonical_type = _parse_canonical_type(tipo_canonico)

        with SessionLocal() as db:
            effective_tenant_id = _effective_tenant_id(db)
            item = AlertTypeAlias(
                tenant_id=effective_tenant_id,
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
            payload = to_dict(item)
            return {"ok": True, "tipo_alerta": payload}

    @tool
    def atualizar_tipo_alerta(
        tipo_id: str | None = None,
        alias: str | None = None,
        novo_alias: str | None = None,
        tipo_canonico: str | None = None,
        descricao: str | None = None,
        ativo: bool | None = None,
    ) -> dict:
        """Atualiza alias, tipo canônico, descrição e status de um tipo de alerta cadastrado."""
        assert_permission(actor_level, "update", "alert_types")
        with SessionLocal() as db:
            item = _get_alias(db, tipo_id=tipo_id, alias=alias, tenant_id=tenant_id)
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
            payload = to_dict(item)
            return {"ok": True, "tipo_alerta": payload}

    @tool
    def deletar_tipo_alerta(tipo_id: str | None = None, alias: str | None = None) -> dict:
        """Remove um alias de tipo de alerta cadastrado."""
        assert_permission(actor_level, "delete", "alert_types")
        with SessionLocal() as db:
            item = _get_alias(db, tipo_id=tipo_id, alias=alias, tenant_id=tenant_id)
            if not item:
                return {"ok": False, "message": "Tipo de alerta não encontrado."}

            removed_alias = item.alias
            db.delete(item)
            db.commit()
            return {"ok": True, "message": "Tipo de alerta removido com sucesso.", "alias": removed_alias}

    return [
        listar_tipos_alerta,
        obter_tipo_alerta,
        criar_tipo_alerta,
        atualizar_tipo_alerta,
        deletar_tipo_alerta,
    ]
