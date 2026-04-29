from datetime import datetime, date, time
import uuid
from enum import Enum

from sqlalchemy import Boolean, Column, Date, DateTime, DECIMAL, Enum as SQLEnum, ForeignKey, Integer, SmallInteger, String, Text, UniqueConstraint, func, BigInteger
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
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
    DIREITO = "direito"
    ESQUERDO = "esquerdo"


class AlertType(str, Enum):
    MAQUINA_QUEBRADA = "maquina_quebrada"
    ACIDENTE = "acidente"
    FALTA_MATERIAL = "falta_material"
    RISCO_SEGURANCA = "risco_seguranca"
    OUTRO = "outro"


class AlertSeverity(str, Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "critica"


class AlertStatus(str, Enum):
    ABERTO = "aberto"
    EM_ATENDIMENTO = "em_atendimento"
    AGUARDANDO_PECA = "aguardando_peca"
    RESOLVIDO = "resolvido"
    CANCELADO = "cancelado"


class CanalOrigemMensagem(str, Enum):
    TELEGRAM = "telegram"


class ConteudoMensagemTipo(str, Enum):
    TEXTO = "texto"
    FOTO = "foto"
    AUDIO = "audio"
    MISTO = "misto"


class ProcessamentoMensagemStatus(str, Enum):
    PENDENTE = "pendente"
    PROCESSADA = "processada"
    ERRO = "erro"


class DirecaoMensagem(str, Enum):
    USER = "user"
    AGENT = "agent"


class RegistroStatus(str, Enum):
    PENDENTE = "pendente"
    CONSOLIDADO = "consolidado"
    REVISADO = "revisado"
    ATIVO = "ativo"
    DESCARTADO = "descartado"


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
    alerts_reportados = relationship(
        "Alert",
        back_populates="reporter",
        foreign_keys="Alert.reported_by",
    )
    alerts_resolvidos = relationship(
        "Alert",
        back_populates="resolver",
        foreign_keys="Alert.resolved_by",
    )
    alerts_lidos = relationship(
        "Alert",
        back_populates="reader",
        foreign_keys="Alert.read_by",
    )
    alert_reads = relationship(
        "AlertRead",
        back_populates="worker",
        foreign_keys="AlertRead.worker_id",
    )
    mensagens_campo = relationship("MensagemCampo", back_populates="usuario")

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
    status = Column(
        SQLEnum(RegistroStatus, values_callable=_enum_values, name="registro_status"),
        nullable=False,
        default=RegistroStatus.PENDENTE,
        index=True,
    )
    data = Column(Date, nullable=True, index=True)
    frente_servico_id = Column(Integer, ForeignKey("frentes_servico.id", ondelete="CASCADE"), nullable=True, index=True)
    usuario_registrador_id = Column(Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=True, index=True)
    estaca_inicial = Column(DECIMAL(10, 2), nullable=True)
    estaca_final = Column(DECIMAL(10, 2), nullable=True)
    resultado = Column(DECIMAL(10, 2), nullable=True)
    tempo_manha = Column(SQLEnum(Clima, values_callable=_enum_values, name="clima"), nullable=True)
    tempo_tarde = Column(SQLEnum(Clima, values_callable=_enum_values, name="clima"), nullable=True)
    lado_pista = Column(SQLEnum(LadoPista, values_callable=_enum_values, name="lado_pista_enum"), nullable=True)
    observacao = Column(String, nullable=True)
    raw_text = Column(Text, nullable=True)
    source_message_id = Column(PGUUID(as_uuid=True), ForeignKey("mensagens_campo.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    frente_servico = relationship("FrenteServico", back_populates="registros")
    usuario_registrador = relationship("Usuario", back_populates="registros")
    source_message = relationship("MensagemCampo", back_populates="registros")
    imagens = relationship(
        "RegistroImagem",
        back_populates="registro",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def pista(self):
        return self.lado_pista

    @pista.setter
    def pista(self, value):
        self.lado_pista = value


class RegistroImagem(Base):
    __tablename__ = "registro_imagens"

    id = Column(Integer, primary_key=True, index=True)
    registro_id = Column(Integer, ForeignKey("registros.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_path = Column(String, nullable=True)
    external_url = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    origem = Column(String, nullable=False, default="api")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    registro = relationship("Registro", back_populates="imagens")


class MensagemCampo(Base):
    __tablename__ = "mensagens_campo"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canal = Column(SQLEnum(CanalOrigemMensagem, values_callable=_enum_values, name="canal_origem_mensagem"), nullable=False)
    telegram_chat_id = Column(String, nullable=True, index=True)
    telegram_message_id = Column(BigInteger, nullable=True)
    telegram_update_id = Column(BigInteger, nullable=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    recebida_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    tipo_conteudo = Column(
        SQLEnum(ConteudoMensagemTipo, values_callable=_enum_values, name="conteudo_mensagem_tipo"),
        nullable=False,
        default=ConteudoMensagemTipo.TEXTO,
    )
    texto_bruto = Column(Text, nullable=True)
    texto_normalizado = Column(Text, nullable=True)
    payload_json = Column(Text, nullable=True)
    hash_idempotencia = Column(String(120), nullable=True, unique=True, index=True)
    processada_em = Column(DateTime(timezone=True), nullable=True)
    status_processamento = Column(
        SQLEnum(ProcessamentoMensagemStatus, values_callable=_enum_values, name="processamento_mensagem_status"),
        nullable=False,
        default=ProcessamentoMensagemStatus.PENDENTE,
        index=True,
    )
    erro_processamento = Column(Text, nullable=True)
    direcao = Column(
        SQLEnum(DirecaoMensagem, values_callable=_enum_values, name="direcao_mensagem"),
        nullable=False,
        default=DirecaoMensagem.USER,
        index=True,
    )

    usuario = relationship("Usuario", back_populates="mensagens_campo")
    registros = relationship("Registro", back_populates="source_message")


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


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(20), unique=True, nullable=False, index=True)
    type = Column(String(120), nullable=False, index=True)
    severity = Column(SQLEnum(AlertSeverity, values_callable=_enum_values, name="alert_severity"), nullable=False)
    reported_by = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    telegram_message_id = Column(BigInteger, nullable=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    raw_text = Column(Text, nullable=True)
    location_detail = Column(String(200), nullable=True)
    equipment_name = Column(String(100), nullable=True)
    photo_urls = Column(ARRAY(String), nullable=True)
    status = Column(
        SQLEnum(AlertStatus, values_callable=_enum_values, name="alert_status"),
        nullable=False,
        default=AlertStatus.ABERTO,
    )
    priority_score = Column(SmallInteger, nullable=True)
    notified_at = Column(DateTime(timezone=True), nullable=True)
    notified_channels = Column(ARRAY(String), nullable=True)
    resolved_by = Column(Integer, ForeignKey("usuarios.id"), nullable=True, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    read_by = Column(Integer, ForeignKey("usuarios.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    reporter = relationship("Usuario", back_populates="alerts_reportados", foreign_keys=[reported_by])
    resolver = relationship("Usuario", back_populates="alerts_resolvidos", foreign_keys=[resolved_by])
    reader = relationship("Usuario", back_populates="alerts_lidos", foreign_keys=[read_by])
    reads = relationship(
        "AlertRead",
        back_populates="alert",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AlertRead(Base):
    __tablename__ = "alert_reads"
    __table_args__ = (
        UniqueConstraint("alert_id", "worker_id", name="uq_alert_reads_alert_worker"),
    )

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id = Column(PGUUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True)
    worker_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    alert = relationship("Alert", back_populates="reads")
    worker = relationship("Usuario", back_populates="alert_reads", foreign_keys=[worker_id])


class AlertTypeAlias(Base):
    __tablename__ = "alert_type_aliases"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alias = Column(String(120), nullable=False, unique=True)
    normalized_alias = Column(String(120), nullable=False, unique=True, index=True)
    canonical_type = Column(String(120), nullable=False, index=True)
    descricao = Column(Text, nullable=True)
    ativo = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_by = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
