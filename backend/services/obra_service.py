"""Serviço de obras operacionais."""
from __future__ import annotations

from backend.agents.tools.database.common import assert_permission, to_dict
from backend.db.repository import Repository
from backend.db.session import SessionLocal


def listar_obras(tenant_id: int) -> list[dict]:
    with SessionLocal() as db:
        obras = Repository.obras.listar(db, tenant_id=tenant_id)
        return [to_dict(o) for o in obras]


def obter_obra(tenant_id: int, obra_id: int) -> dict:
    with SessionLocal() as db:
        obra = Repository.obras.obter_por_id(db, obra_id, tenant_id=tenant_id)
        if not obra:
            return {"ok": False, "message": "Obra não encontrada."}
        return {"ok": True, "obra": to_dict(obra)}


def criar_obra(
    tenant_id: int,
    actor_level: str,
    *,
    nome: str,
    codigo: str | None = None,
    descricao: str | None = None,
    ativo: bool = True,
    tipo_obra: str | None = None,
    tipo_obra_id: int | None = None,
) -> dict:
    assert_permission(actor_level, "create", "frentes_servico")
    with SessionLocal() as db:
        obra = Repository.obras.criar(
            db,
            nome=nome,
            codigo=codigo,
            descricao=descricao,
            ativo=ativo,
            tipo_obra=tipo_obra,
            tipo_obra_id=tipo_obra_id,
            tenant_id=tenant_id,
        )
        return {"ok": True, "obra": to_dict(obra)}


def atualizar_obra(
    tenant_id: int,
    actor_level: str,
    obra_id: int,
    *,
    nome: str | None = None,
    codigo: str | None = None,
    descricao: str | None = None,
    ativo: bool | None = None,
) -> dict:
    assert_permission(actor_level, "update", "frentes_servico")
    with SessionLocal() as db:
        obra = Repository.obras.atualizar(
            db, obra_id, tenant_id=tenant_id,
            nome=nome, codigo=codigo, descricao=descricao, ativo=ativo,
        )
        if not obra:
            return {"ok": False, "message": "Obra não encontrada."}
        return {"ok": True, "obra": to_dict(obra)}


def deletar_obra(tenant_id: int, actor_level: str, obra_id: int) -> dict:
    assert_permission(actor_level, "delete", "frentes_servico")
    with SessionLocal() as db:
        ok = Repository.obras.deletar(db, obra_id, tenant_id=tenant_id)
        return {"ok": ok}
