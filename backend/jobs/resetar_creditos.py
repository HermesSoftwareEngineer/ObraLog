"""Job: resetar ciclo mensal de créditos.

Verifica tenants com proximo_reset_em <= now() e repõe creditos_plano.
Execução sugerida: diariamente via cron externo.

Usage:
    python -m backend.jobs.resetar_creditos
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

logger = logging.getLogger("obralog.jobs.resetar_creditos")


def run() -> None:
    from backend.db.session import SessionLocal
    from backend.db.models import TenantAssinatura
    from backend.services.credito_service import resetar_ciclo_mensal

    with SessionLocal() as db:
        agora = datetime.now(timezone.utc)
        assinaturas = (
            db.query(TenantAssinatura)
            .filter(
                TenantAssinatura.proximo_reset_em <= agora,
                TenantAssinatura.status == "ativa",
            )
            .all()
        )
        tenant_ids = [a.tenant_id for a in assinaturas]

    if not tenant_ids:
        logger.info("Nenhuma assinatura para resetar.")
        return

    logger.info("Resetando %d assinatura(s).", len(tenant_ids))
    for tenant_id in tenant_ids:
        try:
            with SessionLocal() as db:
                resetar_ciclo_mensal(db, tenant_id)
            logger.info("[reset] tenant_id=%d resetado com sucesso.", tenant_id)
        except Exception as exc:
            logger.error("[reset] ERRO tenant_id=%d: %s", tenant_id, exc)

    logger.info("Job concluído.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    run()
