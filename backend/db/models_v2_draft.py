from datetime import datetime, date
import uuid
from sqlalchemy import Column, Date, DateTime, DECIMAL, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Diario(Base):
    __tablename__ = "diarios"
    id = Column(Integer, primary_key=True, index=True)
    data = Column(Date, nullable=False, index=True)
    frente_servico_id = Column(Integer, index=True) # Reference to frentes_servico
    usuario_registrador_id = Column(Integer, index=True)
    clima_manha = Column(String, nullable=True)
    clima_tarde = Column(String, nullable=True)
    observacoes_gerais = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    atividades = relationship("Atividade", back_populates="diario", cascade="all, delete-orphan")

class Atividade(Base):
    __tablename__ = "atividades"
    id = Column(Integer, primary_key=True, index=True)
    diario_id = Column(Integer, ForeignKey("diarios.id"), nullable=False)
    descricao = Column(Text, nullable=False)
    estaca_inicial = Column(String, nullable=True)
    estaca_final = Column(String, nullable=True)
    pista = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    diario = relationship("Diario", back_populates="atividades")
    producoes = relationship("Producao", back_populates="atividade", cascade="all, delete-orphan")
    equipamentos = relationship("AtividadeEquipamento", back_populates="atividade", cascade="all, delete-orphan")

class Producao(Base):
    __tablename__ = "producoes"
    id = Column(Integer, primary_key=True, index=True)
    atividade_id = Column(Integer, ForeignKey("atividades.id"), nullable=False)
    quantidade = Column(DECIMAL(10, 2), nullable=False)
    unidade_medida = Column(String, nullable=False)

    atividade = relationship("Atividade", back_populates="producoes")

class AtividadeEquipamento(Base):
    __tablename__ = "atividade_equipamentos"
    id = Column(Integer, primary_key=True, index=True)
    atividade_id = Column(Integer, ForeignKey("atividades.id"), nullable=False)
    equipamento_nome = Column(String, nullable=False)

    atividade = relationship("Atividade", back_populates="equipamentos")
