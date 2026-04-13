from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/api/v2/diarios", tags=["Diarios v2"])

class AtividadeCreate(BaseModel):
    descricao: str
    estaca_inicial: Optional[str] = None
    estaca_final: Optional[str] = None
    quantidade_producao: Optional[float] = None
    unidade_medida: Optional[str] = None
    equipamentos: Optional[List[str]] = []

class DiarioCreate(BaseModel):
    data: str
    frente_servico_id: int
    clima: Optional[str] = None

@router.post("/")
def criar_diario(diario: DiarioCreate):
    """Cria um novo cabeçalho de diário de obra para o dia e frente de serviço específicos."""
    # TODO: Integrar com SQLAlchemy (Diario)
    return {"msg": "Diário criado com sucesso", "data": diario}

@router.post("/{diario_id}/atividades")
def adicionar_atividade(diario_id: int, atividade: AtividadeCreate):
    """Adiciona uma atividade fracionada (com estacas, produção e equipamentos) a um diário existente."""
    # TODO: Integrar com SQLAlchemy (Atividade, Producao, AtividadeEquipamento)
    return {"msg": "Atividade adicionada", "diario_id": diario_id, "atividade": atividade}
