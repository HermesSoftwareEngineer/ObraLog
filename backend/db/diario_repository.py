from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, selectinload

from backend.db.models import Clima, FrenteServico, Registro, RegistroImagem, Usuario


def get_registros_por_periodo(
    session: Session,
    data_inicio: date,
    data_fim: date,
    frente_servico_id: int | None = None,
    usuario_id: int | None = None,
    apenas_impraticaveis: bool = False,
) -> list[Registro]:
    """
    Retorna registros no periodo com joins de frente e usuario.
    Ordenacao: data ASC, frente_servico_id ASC, id ASC.
    """
    query = (
        select(Registro)
        .join(FrenteServico, Registro.frente_servico_id == FrenteServico.id)
        .join(Usuario, Registro.usuario_registrador_id == Usuario.id)
        .options(selectinload(Registro.frente_servico).selectinload(FrenteServico.encarregado))
        .options(selectinload(Registro.usuario_registrador))
        .where(Registro.data >= data_inicio)
        .where(Registro.data <= data_fim)
        .order_by(Registro.data.asc(), Registro.frente_servico_id.asc(), Registro.id.asc())
    )

    if frente_servico_id is not None:
        query = query.where(Registro.frente_servico_id == frente_servico_id)

    if usuario_id is not None:
        query = query.where(Registro.usuario_registrador_id == usuario_id)

    if apenas_impraticaveis:
        query = query.where(
            and_(
                Registro.tempo_manha == Clima.IMPRATICAVEL,
                Registro.tempo_tarde == Clima.IMPRATICAVEL,
            )
        )

    registros = list(session.execute(query).scalars().all())
    if not registros:
        return []

    registro_ids = [item.id for item in registros]
    imagens_query = (
        select(RegistroImagem)
        .where(RegistroImagem.registro_id.in_(registro_ids))
        .order_by(RegistroImagem.registro_id.asc(), RegistroImagem.created_at.asc())
    )
    imagens = list(session.execute(imagens_query).scalars().all())

    imagens_por_registro: dict[int, list[RegistroImagem]] = defaultdict(list)
    for imagem in imagens:
        imagens_por_registro[imagem.registro_id].append(imagem)

    for registro in registros:
        setattr(registro, "_imagens_cache", imagens_por_registro.get(registro.id, []))

    return registros


def get_diario_do_dia(
    session: Session,
    data: date,
    frente_servico_id: int | None = None,
) -> list[Registro]:
    """Atalho para get_registros_por_periodo com data_inicio == data_fim."""
    return get_registros_por_periodo(
        session=session,
        data_inicio=data,
        data_fim=data,
        frente_servico_id=frente_servico_id,
    )


def agrupar_por_data(registros: list[Registro]) -> dict[date, list[Registro]]:
    """Agrupa registros por data com chaves ordenadas."""
    grouped: dict[date, list[Registro]] = defaultdict(list)
    for item in registros:
        grouped[item.data].append(item)

    ordered: dict[date, list[Registro]] = {}
    for key in sorted(grouped.keys()):
        ordered[key] = grouped[key]
    return ordered
