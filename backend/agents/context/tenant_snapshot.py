"""Builds a concise tenant context block injected into the agent system message."""
from __future__ import annotations
from sqlalchemy.orm import Session, joinedload


_LIMIT = 10  # número máximo de itens exibidos por bloco


def _obras_block(db: Session, Obra, tenant_id: int, obra_id_ativa: int | None) -> list[str]:
    # 1 query em vez de 3 (count + first + last) — sem N+1
    obras = (
        db.query(Obra)
        .filter(Obra.tenant_id == tenant_id, Obra.ativo == True)
        .order_by(Obra.created_at.asc())
        .limit(_LIMIT)
        .all()
    )

    lines = [f"\nObras ativas:"]
    if not obras:
        lines.append("  (nenhuma obra ativa cadastrada)")
        return lines

    def _fmt(o: "Obra") -> str:
        cod   = f" [{o.codigo}]" if o.codigo else ""
        ativa = " ← ativa" if o.id == obra_id_ativa else ""
        return f"  - ID {o.id}: {o.nome}{cod}{ativa}"

    for o in obras:
        lines.append(_fmt(o))

    return lines


def _frentes_block(
    db: Session,
    FrenteServico,
    tenant_id: int,
    obra_id_ativa: int | None,
) -> list[str]:
    if obra_id_ativa is not None:
        q = (
            db.query(FrenteServico)
            .filter(
                FrenteServico.tenant_id == tenant_id,
                FrenteServico.obra_id == obra_id_ativa,
            )
        )
        header = f"Frentes de serviço da obra ativa (ID {obra_id_ativa})"
    else:
        q = db.query(FrenteServico).filter(FrenteServico.tenant_id == tenant_id)
        header = "Frentes de serviço do tenant"

    # joinedload evita N+1: encarregado carregado em 1 query via JOIN
    frentes = (
        q.options(joinedload(FrenteServico.encarregado))
        .order_by(FrenteServico.id.asc())
        .limit(_LIMIT)
        .all()
    )

    lines = [f"\n{header}:"]
    if not frentes:
        lines.append("  (nenhuma frente de serviço cadastrada)")
        return lines

    def _fmt(f) -> str:
        enc       = f.encarregado.nome if f.encarregado else "sem encarregado"
        obra_info = f" | obra ID {f.obra_id}" if obra_id_ativa is None and f.obra_id else ""
        return f"  - ID {f.id}: {f.nome} | {enc}{obra_info}"

    for f in frentes:
        lines.append(_fmt(f))

    return lines


def build_tenant_snapshot(
    db: Session,
    tenant_id: int,
    obra_id_ativa: int | None = None,
    actor_level: str | None = None,
) -> str:
    try:
        from backend.db.models import Tenant, Obra, FrenteServico, Registro, RegistroStatus
    except ImportError:
        from db.models import Tenant, Obra, FrenteServico, Registro, RegistroStatus  # type: ignore

    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        return ""

    nome_empresa = tenant.nome_fantasia or tenant.nome
    tipo = tenant.tipo_negocio or "não informado"

    lines: list[str] = [
        "=== Resumo do tenant ===",
        f"Empresa: {nome_empresa} | Tipo: {tipo}",
    ]

    lines += _obras_block(db, Obra, tenant_id, obra_id_ativa)
    lines += _frentes_block(db, FrenteServico, tenant_id, obra_id_ativa)

    if actor_level in ("gerente", "administrador") and obra_id_ativa is not None:
        pendentes = (
            db.query(Registro)
            .filter(
                Registro.tenant_id == tenant_id,
                Registro.obra_id == obra_id_ativa,
                Registro.status == RegistroStatus.PENDENTE,
            )
            .count()
        )
        if pendentes > 0:
            lines.append(
                f"\nAtenção: {pendentes} registro(s) pendente(s) de aprovação na obra ativa."
            )

    return "\n".join(lines)
