"""Business logic for generating and managing Diários de Obra."""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.db.models import (
    Diario, DiarioRegistro, DiarioStatus, DiarioTipo, DiarioVersao,
    FrenteServico, Obra, Registro, RegistroSchema, RegistroStatus, Tenant, Usuario,
)
from backend.db.session import SessionLocal

logger = logging.getLogger("obralog.diario_service")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _diario_to_dict(diario: Diario, versoes: list[DiarioVersao] | None = None) -> dict:
    obra_nome = diario.obra.nome if getattr(diario, "obra", None) else None
    return {
        "id": str(diario.id),
        "obra_id": diario.obra_id,
        "obra_nome": obra_nome,
        "tenant_id": diario.tenant_id,
        "tipo": diario.tipo.value if hasattr(diario.tipo, "value") else str(diario.tipo),
        "status": diario.status.value if hasattr(diario.status, "value") else str(diario.status),
        "data_inicio": diario.data_inicio.isoformat() if diario.data_inicio else None,
        "data_fim": diario.data_fim.isoformat() if diario.data_fim else None,
        "versao_atual": diario.versao_atual,
        "gerado_em": diario.gerado_em.isoformat() if diario.gerado_em else None,
        "finalizado_em": diario.finalizado_em.isoformat() if diario.finalizado_em else None,
        "versoes": [_versao_to_dict(v) for v in (versoes or [])],
    }


def _versao_to_dict(versao: DiarioVersao) -> dict:
    return {
        "id": str(versao.id),
        "versao": versao.versao,
        "storage_path": versao.storage_path,
        "storage_url": versao.storage_url,
        "gerado_em": versao.gerado_em.isoformat() if versao.gerado_em else None,
        "motivo_regeracao": versao.motivo_regeracao,
        "include_pending": bool(versao.include_pending),
    }


def _get_registros_para_diario(
    db: Session, obra_id: int, tenant_id: int, data_inicio: date, data_fim: date,
    include_pending: bool = False,
) -> list[Registro]:
    statuses = [RegistroStatus.APROVADO]
    if include_pending:
        statuses.append(RegistroStatus.PENDENTE)
    # Registros podem ter obra_id nulo quando criados via bot sem obra explícita.
    # Nesses casos, a obra é derivada de FrenteServico.obra_id.
    return (
        db.query(Registro)
        .outerjoin(FrenteServico, Registro.frente_servico_id == FrenteServico.id)
        .options(selectinload(Registro.frente_servico), selectinload(Registro.imagens))
        .filter(
            Registro.tenant_id == tenant_id,
            Registro.status.in_(statuses),
            Registro.data >= data_inicio,
            Registro.data <= data_fim,
            or_(
                Registro.obra_id == obra_id,
                and_(Registro.obra_id.is_(None), FrenteServico.obra_id == obra_id),
            ),
        )
        .order_by(Registro.data.asc(), Registro.id.asc())
        .all()
    )


def _registro_to_row(r: Registro, include_imagens: bool = False) -> dict:
    frente_nome = None
    if getattr(r, "frente_servico", None):
        frente_nome = r.frente_servico.nome
    row: dict = {
        "id": r.id,
        "data": r.data.isoformat() if r.data else None,
        "frente_servico_id": r.frente_servico_id,
        "frente_servico_nome": frente_nome,
        "registro_schema_id": r.registro_schema_id,
        "estaca_inicial": float(r.estaca_inicial) if r.estaca_inicial is not None else None,
        "estaca_final": float(r.estaca_final) if r.estaca_final is not None else None,
        "localizacao": r.localizacao,
        "resultado": float(r.resultado) if r.resultado is not None else None,
        "lado_pista": r.lado_pista.value if hasattr(r.lado_pista, "value") else str(r.lado_pista or ""),
        "tempo_manha": r.tempo_manha.value if hasattr(r.tempo_manha, "value") else str(r.tempo_manha or ""),
        "tempo_tarde": r.tempo_tarde.value if hasattr(r.tempo_tarde, "value") else str(r.tempo_tarde or ""),
        "observacao": r.observacao,
        "status": r.status.value if hasattr(r.status, "value") else str(r.status or ""),
        "metadata_json": r.metadata_json or {},
    }
    if include_imagens:
        row["imagens"] = [
            {
                "id": img.id,
                "storage_path": img.storage_path,
                "external_url": img.external_url,
                "mime_type": img.mime_type,
            }
            for img in (getattr(r, "imagens", None) or [])
        ]
    return row


def _build_frentes_schemas(db: Session, registros: list[Registro]) -> dict:
    """Builds {frente_id: {"nome": str, "campos_ativos": dict, "campos_extras": list}}."""
    result: dict = {}
    schema_cache: dict = {}
    for r in registros:
        frente = getattr(r, "frente_servico", None)
        fid = frente.id if frente else None
        if fid in result:
            continue
        schema_id = (frente.registro_schema_id if frente else None) or r.registro_schema_id
        schema = None
        if schema_id:
            if schema_id not in schema_cache:
                schema_cache[schema_id] = db.query(RegistroSchema).filter(RegistroSchema.id == schema_id).first()
            schema = schema_cache.get(schema_id)
        campos_ativos = schema.campos_ativos if (schema and isinstance(getattr(schema, "campos_ativos", None), dict)) else {}
        campos_extras = schema.campos_extras if (schema and isinstance(getattr(schema, "campos_extras", None), list)) else []
        logger.info(
            "[_build_frentes_schemas] fid=%s frente=%s schema_id=%s schema_found=%s "
            "campos_ativos=%s campos_extras_count=%s",
            fid,
            frente.nome if frente else None,
            schema_id,
            schema is not None,
            campos_ativos,
            len(campos_extras),
        )
        result[fid] = {
            "nome": frente.nome if frente else "Sem frente",
            "campos_ativos": campos_ativos,
            "campos_extras": campos_extras,
        }
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def gerar_ou_regerar_diario(
    obra_id: int,
    tenant_id: int,
    tipo: str,
    data_inicio: date,
    data_fim: date,
    gerado_por: int | None,
    motivo_regeracao: str | None = None,
    include_pending: bool = False,
) -> dict:
    """Create or regenerate a diário for the given obra/period. Returns DiarioResponse dict."""
    from backend.services.pdf_service import gerar_pdf_diario
    from backend.utils.storage import upload_pdf_diario, get_signed_url_diario

    with SessionLocal() as db:
        obra = db.query(Obra).filter(Obra.id == obra_id, Obra.tenant_id == tenant_id).first()
        if not obra:
            raise ValueError(f"Obra {obra_id} não encontrada para o tenant.")

        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        tenant_nome = tenant.nome if tenant else str(tenant_id)

        registros = _get_registros_para_diario(db, obra_id, tenant_id, data_inicio, data_fim, include_pending=include_pending)

        # Upsert diario
        diario = (
            db.query(Diario)
            .filter(
                Diario.obra_id == obra_id,
                Diario.tenant_id == tenant_id,
                Diario.tipo == tipo,
                Diario.data_inicio == data_inicio,
                Diario.data_fim == data_fim,
            )
            .first()
        )

        is_novo = diario is None
        if is_novo:
            diario = Diario(
                obra_id=obra_id,
                tenant_id=tenant_id,
                tipo=tipo,
                data_inicio=data_inicio,
                data_fim=data_fim,
                versao_atual=1,
                gerado_por=gerado_por,
                status="rascunho",
            )
            db.add(diario)
            db.flush()  # get the UUID
        else:
            diario.versao_atual += 1
            # Regerar após finalizado volta para rascunho
            diario.status = "rascunho"
            diario.gerado_por = gerado_por

        versao_num = diario.versao_atual
        diario_id_str = str(diario.id)

        # Rebuild diario_registros
        db.query(DiarioRegistro).filter(DiarioRegistro.diario_id == diario.id).delete()
        for r in registros:
            db.add(DiarioRegistro(diario_id=diario.id, registro_id=r.id, tenant_id=tenant_id))

        db.flush()

        # Build PDF data
        gerado_por_user = db.query(Usuario).filter(Usuario.id == gerado_por).first() if gerado_por else None
        gerado_por_nome = gerado_por_user.nome if gerado_por_user else "sistema"
        registros_rows = [_registro_to_row(r, include_imagens=True) for r in registros]
        frentes_schemas = _build_frentes_schemas(db, registros)

        diario_info = {
            "obra_id": obra_id,
            "obra_nome": obra.nome,
            "tenant_nome": tenant_nome,
            "tipo": tipo,
            "data_inicio": data_inicio.isoformat(),
            "data_fim": data_fim.isoformat(),
            "versao_atual": versao_num,
            "status": "rascunho",
            "gerado_por_nome": gerado_por_nome,
            "gerado_em": datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M"),
        }

        # Generate PDF
        try:
            pdf_bytes = gerar_pdf_diario(diario_info, registros_rows, frentes_schemas)
        except Exception as exc:
            db.rollback()
            raise RuntimeError(f"Falha ao gerar PDF: {exc}") from exc

        # Upload to Storage
        try:
            storage_path = upload_pdf_diario(tenant_id, diario_id_str, versao_num, pdf_bytes)
            storage_url = get_signed_url_diario(storage_path)
        except Exception as exc:
            db.rollback()
            raise RuntimeError(f"Falha ao fazer upload do PDF: {exc}") from exc

        # Create versao record
        versao_obj = DiarioVersao(
            diario_id=diario.id,
            tenant_id=tenant_id,
            versao=versao_num,
            storage_path=storage_path,
            storage_url=storage_url,
            gerado_por=gerado_por,
            motivo_regeracao=motivo_regeracao if not is_novo else None,
            registros_ids=[r.id for r in registros],
            include_pending=include_pending,
        )
        db.add(versao_obj)

        now = datetime.now(timezone.utc)
        diario.gerado_em = now
        diario.updated_at = now

        db.commit()
        db.refresh(diario)
        db.refresh(versao_obj)

        versoes = (
            db.query(DiarioVersao)
            .filter(DiarioVersao.diario_id == diario.id)
            .order_by(DiarioVersao.versao.desc())
            .all()
        )

        return _diario_to_dict(diario, versoes)


def finalizar_diario(diario_id: str, finalizado_por: int, tenant_id: int | None = None) -> dict:
    """Mark a diário as finalizado."""
    with SessionLocal() as db:
        q = db.query(Diario).filter(Diario.id == diario_id)
        if tenant_id is not None:
            q = q.filter(Diario.tenant_id == tenant_id)
        diario = q.first()
        if not diario:
            raise ValueError(f"Diário {diario_id} não encontrado.")

        diario.status = "finalizado"
        diario.finalizado_por = finalizado_por
        diario.finalizado_em = datetime.now(timezone.utc)
        diario.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(diario)

        versoes = (
            db.query(DiarioVersao)
            .filter(DiarioVersao.diario_id == diario.id)
            .order_by(DiarioVersao.versao.desc())
            .all()
        )
        return _diario_to_dict(diario, versoes)


def get_dados_para_exportar(diario_id: str, versao: int, tenant_id: int) -> tuple[dict, list[dict]]:
    """Returns (diario_info, registros_rows) for a specific versão, for export."""
    with SessionLocal() as db:
        from backend.db.models import DiarioVersao as DV
        versao_obj = (
            db.query(DV)
            .filter(DV.diario_id == diario_id, DV.versao == versao, DV.tenant_id == tenant_id)
            .first()
        )
        if not versao_obj:
            raise ValueError(f"Versão {versao} do diário {diario_id} não encontrada.")

        diario = (
            db.query(Diario)
            .filter(Diario.id == diario_id, Diario.tenant_id == tenant_id)
            .first()
        )
        if not diario:
            raise ValueError(f"Diário {diario_id} não encontrado.")

        obra_nome = diario.obra.nome if getattr(diario, "obra", None) else None
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        tenant_nome = tenant.nome if tenant else str(tenant_id)

        gerado_por_user = db.query(Usuario).filter(Usuario.id == versao_obj.gerado_por).first() if versao_obj.gerado_por else None
        gerado_por_nome = gerado_por_user.nome if gerado_por_user else "sistema"

        diario_info = {
            "obra_id": diario.obra_id,
            "obra_nome": obra_nome,
            "tenant_nome": tenant_nome,
            "tipo": diario.tipo.value if hasattr(diario.tipo, "value") else str(diario.tipo),
            "data_inicio": diario.data_inicio.isoformat() if diario.data_inicio else None,
            "data_fim": diario.data_fim.isoformat() if diario.data_fim else None,
            "versao_atual": versao,
            "status": diario.status.value if hasattr(diario.status, "value") else str(diario.status),
            "gerado_por_nome": gerado_por_nome,
        }

        registros_ids = versao_obj.registros_ids or []
        if registros_ids:
            regs = (
                db.query(Registro)
                .options(selectinload(Registro.frente_servico), selectinload(Registro.imagens))
                .filter(Registro.id.in_(registros_ids), Registro.tenant_id == tenant_id)
                .order_by(Registro.data.asc(), Registro.id.asc())
                .all()
            )
        else:
            regs = _get_registros_para_diario(
                db, diario.obra_id, tenant_id,
                diario.data_inicio, diario.data_fim,
                include_pending=bool(versao_obj.include_pending),
            )

        registros_rows = [_registro_to_row(r, include_imagens=True) for r in regs]
        frentes_schemas = _build_frentes_schemas(db, regs)
        return diario_info, registros_rows, frentes_schemas


def deletar_diario(diario_id: str, tenant_id: int) -> None:
    """Delete a diário and all related records. Raises ValueError if not found."""
    with SessionLocal() as db:
        diario = (
            db.query(Diario)
            .filter(Diario.id == diario_id, Diario.tenant_id == tenant_id)
            .first()
        )
        if not diario:
            raise ValueError(f"Diário {diario_id} não encontrado.")
        db.query(DiarioRegistro).filter(DiarioRegistro.diario_id == diario.id).delete()
        db.query(DiarioVersao).filter(DiarioVersao.diario_id == diario.id).delete()
        db.delete(diario)
        db.commit()


def buscar_diario(
    obra_id: int,
    tenant_id: int,
    tipo: str,
    data_inicio: date,
    data_fim: date,
) -> dict | None:
    """Return an existing diário with all versions, or None if not found."""
    with SessionLocal() as db:
        diario = (
            db.query(Diario)
            .filter(
                Diario.obra_id == obra_id,
                Diario.tenant_id == tenant_id,
                Diario.tipo == tipo,
                Diario.data_inicio == data_inicio,
                Diario.data_fim == data_fim,
            )
            .first()
        )
        if not diario:
            return None

        versoes = (
            db.query(DiarioVersao)
            .filter(DiarioVersao.diario_id == diario.id)
            .order_by(DiarioVersao.versao.desc())
            .all()
        )
        return _diario_to_dict(diario, versoes)
