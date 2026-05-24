"""Cron job: gera/regera diários do tipo 'diario' para o dia atual.

Para cada tenant ativo, para cada obra ativa:
  - verifica se há pelo menos 1 registro aprovado para hoje
  - se sim, chama gerar_ou_regerar_diario

Usage:
    python -m backend.jobs.gerar_diarios_diarios
"""
from __future__ import annotations

import logging
import sys
from datetime import date

from sqlalchemy import text

logger = logging.getLogger("obralog.jobs.gerar_diarios_diarios")


def run() -> None:
    from backend.db.session import SessionLocal
    from backend.db.models import Obra, Registro, RegistroStatus, Tenant
    from backend.services.diario_service import gerar_ou_regerar_diario

    hoje = date.today()
    logger.info("Iniciando geração de diários para %s", hoje.isoformat())

    with SessionLocal() as db:
        tenants = db.query(Tenant).filter(Tenant.ativo.is_(True)).all()

    for tenant in tenants:
        with SessionLocal() as db:
            obras = (
                db.query(Obra)
                .filter(Obra.tenant_id == tenant.id, Obra.ativo.is_(True))
                .all()
            )

        for obra in obras:
            try:
                with SessionLocal() as db:
                    tem_aprovado = (
                        db.query(Registro.id)
                        .filter(
                            Registro.obra_id == obra.id,
                            Registro.tenant_id == tenant.id,
                            Registro.status == RegistroStatus.APROVADO,
                            Registro.data == hoje,
                        )
                        .first()
                    )

                if not tem_aprovado:
                    logger.debug(
                        "Sem registros aprovados — tenant=%d obra=%d data=%s",
                        tenant.id, obra.id, hoje,
                    )
                    continue

                # Use tenant.id as gerado_por (sentinel: 0 = sistema)
                # Using the first admin user of the tenant as fallback, or 0 if none
                gerado_por = _resolve_system_user(tenant.id)

                result = gerar_ou_regerar_diario(
                    obra_id=obra.id,
                    tenant_id=tenant.id,
                    tipo="diario",
                    data_inicio=hoje,
                    data_fim=hoje,
                    gerado_por=gerado_por,
                    motivo_regeracao=None,
                )
                action = "criado" if result.get("versao_atual") == 1 else "regerado"
                logger.info(
                    "Diário %s — tenant=%d obra=%d versao=%d",
                    action, tenant.id, obra.id, result.get("versao_atual"),
                )
            except Exception as exc:
                logger.error(
                    "Erro ao gerar diário — tenant=%d obra=%d: %s",
                    tenant.id, obra.id, exc,
                )

    logger.info("Job concluído.")


def _resolve_system_user(tenant_id: int) -> int | None:
    """Return the first admin user id for the tenant, or None (system run)."""
    from backend.db.session import SessionLocal
    from backend.db.models import Usuario, NivelAcesso

    with SessionLocal() as db:
        user = (
            db.query(Usuario)
            .filter(
                Usuario.tenant_id == tenant_id,
                Usuario.nivel_acesso == NivelAcesso.ADMINISTRADOR,
            )
            .first()
        )
        return user.id if user else None


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    run()
