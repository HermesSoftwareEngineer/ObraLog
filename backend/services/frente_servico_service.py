"""Serviço de frentes de serviço — somente leitura para o agente."""
from __future__ import annotations

from backend.agents.tools.database.common import normalize_text, to_dict
from backend.db.repository import Repository
from backend.db.session import SessionLocal


def listar_frentes(tenant_id: int) -> list[dict]:
    with SessionLocal() as db:
        frentes = Repository.frentes_servico.listar(db, tenant_id=tenant_id)
        return [to_dict(f) for f in frentes]


def obter_frente(
    tenant_id: int,
    frente_id: int | None = None,
    nome: str | None = None,
) -> dict:
    with SessionLocal() as db:
        if frente_id is not None:
            frente = Repository.frentes_servico.obter_por_id(db, frente_id, tenant_id=tenant_id)
        elif nome:
            alvo = normalize_text(nome)
            todas = Repository.frentes_servico.listar(db, tenant_id=tenant_id)
            exatos = [f for f in todas if normalize_text(f.nome) == alvo]
            parciais = [f for f in todas if alvo in normalize_text(f.nome)]
            candidatos = exatos or parciais
            if len(candidatos) == 1:
                frente = candidatos[0]
            elif len(candidatos) > 1:
                return {
                    "ok": False,
                    "message": "Mais de uma frente encontrada. Seja mais específico.",
                    "opcoes": [f.nome for f in candidatos[:8]],
                }
            else:
                frente = None
        else:
            raise ValueError("Informe frente_id ou nome para identificar a frente de serviço.")
        if not frente:
            return {"ok": False, "message": "Frente de serviço não encontrada."}
        return {"ok": True, "frente_servico": to_dict(frente)}
