from datetime import datetime, date, time
from enum import Enum

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Date, Time, DECIMAL, Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass

# =====================
# ENUMS
# =====================

class NivelAcesso(str, Enum):
    ADMINISTRADOR = "administrador"
    GERENTE = "gerente"
    ENCARREGADO = "encarregado"

class Clima(str, Enum):
    LIMPO = "limpo"
    NUBLADO = "nublado"
    IMPRATICAVEL = "impraticavel"

class LadoPista(str, Enum):
    DIREITA = "direita"
    ESQUERDA = "esquerda"


def _enum_values(enum_cls):
    return [item.value for item in enum_cls]

# =====================
# MODELS
# =====================

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    senha = Column(String, nullable=False)
    telefone = Column(String, unique=True, nullable=True, index=True)
    telegram_chat_id = Column(String, unique=True, nullable=True, index=True)
    telegram_thread_id = Column(String, unique=True, nullable=True, index=True)
    nivel_acesso = Column(
        SQLEnum(
            NivelAcesso,
            values_callable=_enum_values,
            name="nivel_acesso",
        ),
        default=NivelAcesso.ENCARREGADO,
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    frentes_servico = relationship("FrenteServico", back_populates="encarregado")
    registros = relationship("Registro", back_populates="usuario_registrador")
    telegram_link_codes = relationship(
        "TelegramLinkCode",
        back_populates="usuario",
        foreign_keys="TelegramLinkCode.user_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

class FrenteServico(Base):
    __tablename__ = "frentes_servico"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    encarregado_responsavel = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    observacao = Column(String, nullable=True)

    encarregado = relationship("Usuario", back_populates="frentes_servico")
    registros = relationship("Registro", back_populates="frente_servico")

class Registro(Base):
    __tablename__ = "registros"

    id = Column(Integer, primary_key=True, index=True)
    data = Column(Date, nullable=True, index=True)
    frente_servico_id = Column(Integer, ForeignKey("frentes_servico.id", ondelete="CASCADE"), nullable=False, index=True)
    usuario_registrador_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    estaca_inicial = Column(DECIMAL(10, 2), nullable=True)
    estaca_final = Column(DECIMAL(10, 2), nullable=True)
    resultado = Column(DECIMAL(10, 2), nullable=True)
    tempo_manha = Column(SQLEnum(Clima, values_callable=_enum_values, name="clima"), nullable=True)
    tempo_tarde = Column(SQLEnum(Clima, values_callable=_enum_values, name="clima"), nullable=True)
    pista = Column(SQLEnum(LadoPista, values_callable=_enum_values, name="lado_pista_enum"), nullable=True)
    lado_pista = Column(SQLEnum(LadoPista, values_callable=_enum_values, name="lado_pista_enum"), nullable=True)
    observacao = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    frente_servico = relationship("FrenteServico", back_populates="registros")
    usuario_registrador = relationship("Usuario", back_populates="registros")


class TelegramLinkCode(Base):
    __tablename__ = "telegram_link_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(32), nullable=False, unique=True, index=True)
    generated_by_user_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    used_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    usuario = relationship("Usuario", foreign_keys=[user_id], back_populates="telegram_link_codes")

