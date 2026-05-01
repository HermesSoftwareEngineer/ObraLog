from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class FrenteServicoSummary(BaseModel):
    id: int
    nome: str
    encarregado: str | None = None


class ImagemOut(BaseModel):
    id: int
    external_url: str | None = None
    storage_path: str | None = None
    mime_type: str | None = None
    origem: str


class LocalizacaoSchema(BaseModel):
    tipo: str  # 'TEXT', 'ESTACA', 'KM'
    detalhe_texto: str | None = None
    valor_inicial: float | None = None
    valor_final: float | None = None


class RegistroOut(BaseModel):
    id: int
    data: date

    frente_servico_id: int
    usuario_registrador_id: int
    estaca_inicial: float | None = None
    estaca_final: float | None = None
    localizacao: LocalizacaoSchema | None = None
    resultado: float | None = None
    tempo_manha: str
    tempo_tarde: str
    pista: str | None = None
    lado_pista: str | None = None
    observacao: str | None = None
    created_at: datetime | None = None
    registrador_nome: str
    imagens: list[ImagemOut] = []


class RegistroCreate(BaseModel):
    data: date
    frente_servico_id: int
    usuario_registrador_id: int
    estaca_inicial: float | None = None
    estaca_final: float | None = None
    localizacao: LocalizacaoSchema | None = None
    resultado: float | None = None
    tempo_manha: str | None = None
    tempo_tarde: str | None = None
    pista: str | None = None
    lado_pista: str | None = None
    observacao: str | None = None


class DiarioDoDiaOut(BaseModel):
    data: date
    frente_servico: FrenteServicoSummary | None = None
    registros: list[RegistroOut]
    total_resultado: float
    total_registros: int
    dias_impraticaveis: bool
    resumo_clima: str


class DiarioRelatorioOut(BaseModel):
    data_inicio: date
    data_fim: date
    dias: list[DiarioDoDiaOut]
    total_resultado_periodo: float
    total_dias: int
    total_dias_impraticaveis: int
    media_diaria: float


class FiltrosDiario(BaseModel):
    data_inicio: date
    data_fim: date
    frente_servico_id: int | None = None
    usuario_id: int | None = None
    apenas_impraticaveis: bool = False

__all__ = [
    "FrenteServicoSummary",
    "ImagemOut",
    "RegistroOut",
    "RegistroCreate",
    "DiarioDoDiaOut",
    "DiarioRelatorioOut",
    "FiltrosDiario",
]
