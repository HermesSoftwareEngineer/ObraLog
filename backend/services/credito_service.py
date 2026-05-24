"""Serviço de créditos — verifica saldo, debita e gerencia ciclos mensais."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

logger = logging.getLogger("obralog.credito_service")

CUSTO_OPERACOES: dict[str, int] = {
    "mensagem_agente":  2,
    "gerar_diario":    10,
    "resumo_conversa":  3,
    "recarga_manual":   0,
    "reset_mensal":     0,
}


def verificar_saldo(db: Session, tenant_id: int) -> bool:
    """Retorna True se o tenant tem créditos disponíveis.

    Se o tenant não tiver assinatura, retorna True (sem bloqueio — tenant em setup).
    """
    from backend.db.models import TenantAssinatura

    assinatura = (
        db.query(TenantAssinatura)
        .filter(TenantAssinatura.tenant_id == tenant_id)
        .first()
    )
    if assinatura is None:
        return True
    return (assinatura.creditos_plano + assinatura.creditos_avulsos) > 0


def debitar_creditos(
    db: Session,
    tenant_id: int,
    operacao: str,
    referencia_id: str | None = None,
) -> bool:
    """Debita créditos da operação.

    Consome primeiro creditos_plano; se insuficiente, usa creditos_avulsos.
    Retorna True se débito realizado, False se saldo insuficiente.
    Não lança exceção — o chamador decide o que fazer.
    """
    from backend.db.models import CreditoTransacao, TenantAssinatura

    custo = CUSTO_OPERACOES.get(operacao, 1)
    if custo <= 0:
        return True

    assinatura = (
        db.query(TenantAssinatura)
        .filter(TenantAssinatura.tenant_id == tenant_id)
        .with_for_update()
        .first()
    )
    if assinatura is None:
        return True

    total = assinatura.creditos_plano + assinatura.creditos_avulsos
    if total < custo:
        return False

    if assinatura.creditos_plano >= custo:
        assinatura.creditos_plano -= custo
    else:
        restante = custo - assinatura.creditos_plano
        assinatura.creditos_plano = 0
        assinatura.creditos_avulsos -= restante

    db.add(CreditoTransacao(
        tenant_id=tenant_id,
        operacao=operacao,
        creditos=-custo,
        descricao=f"Débito automático: {operacao}",
        referencia_id=referencia_id,
    ))
    db.commit()
    return True


def adicionar_creditos_avulsos(
    db: Session,
    tenant_id: int,
    quantidade: int,
    descricao: str | None = None,
) -> None:
    """Incrementa creditos_avulsos da assinatura e registra transação."""
    from backend.db.models import CreditoTransacao, TenantAssinatura

    assinatura = (
        db.query(TenantAssinatura)
        .filter(TenantAssinatura.tenant_id == tenant_id)
        .with_for_update()
        .first()
    )
    if assinatura is None:
        raise ValueError(f"Tenant {tenant_id} não possui assinatura ativa.")

    assinatura.creditos_avulsos += quantidade
    db.add(CreditoTransacao(
        tenant_id=tenant_id,
        operacao="recarga_manual",
        creditos=quantidade,
        descricao=descricao or f"Recarga avulsa: {quantidade} créditos",
        referencia_id=None,
    ))
    db.commit()


def resetar_ciclo_mensal(db: Session, tenant_id: int) -> None:
    """Repõe creditos_plano com o valor do plano e avança proximo_reset_em 30 dias.

    Não toca creditos_avulsos.
    """
    from backend.db.models import CreditoTransacao, Plano, TenantAssinatura

    assinatura = (
        db.query(TenantAssinatura)
        .filter(TenantAssinatura.tenant_id == tenant_id)
        .with_for_update()
        .first()
    )
    if assinatura is None:
        raise ValueError(f"Tenant {tenant_id} não possui assinatura.")

    plano = db.query(Plano).filter(Plano.id == assinatura.plano_id).first()
    if plano is None:
        raise ValueError(f"Plano {assinatura.plano_id} não encontrado.")

    novos_creditos = plano.creditos_mensais
    assinatura.creditos_plano = novos_creditos
    assinatura.proximo_reset_em = datetime.now(timezone.utc) + timedelta(days=30)

    db.add(CreditoTransacao(
        tenant_id=tenant_id,
        operacao="reset_mensal",
        creditos=novos_creditos,
        descricao=f"Reset mensal — plano {plano.nome}: {novos_creditos} créditos",
        referencia_id=None,
    ))
    db.commit()


def consultar_saldo(db: Session, tenant_id: int) -> dict:
    """Retorna saldo atual do tenant.

    Se sem assinatura, retorna total=-1 como sinal de 'sem plano'.
    """
    from backend.db.models import Plano, TenantAssinatura

    assinatura = (
        db.query(TenantAssinatura)
        .filter(TenantAssinatura.tenant_id == tenant_id)
        .first()
    )
    if assinatura is None:
        return {
            "creditos_plano": 0,
            "creditos_avulsos": 0,
            "total": -1,
            "plano": None,
            "proximo_reset_em": None,
        }

    plano = db.query(Plano).filter(Plano.id == assinatura.plano_id).first()
    return {
        "creditos_plano": assinatura.creditos_plano,
        "creditos_avulsos": assinatura.creditos_avulsos,
        "total": assinatura.creditos_plano + assinatura.creditos_avulsos,
        "plano": plano.nome if plano else None,
        "proximo_reset_em": assinatura.proximo_reset_em.isoformat() if assinatura.proximo_reset_em else None,
    }
