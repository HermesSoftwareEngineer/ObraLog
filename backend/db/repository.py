from datetime import date, datetime, time
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from backend.db.models import (
    Usuario,
    FrenteServico,
    Registro,
    RegistroImagem,
    TelegramLinkCode,
    MensagemCampo,
    NivelAcesso,
    CanalOrigemMensagem,
    ConteudoMensagemTipo,
    ProcessamentoMensagemStatus,
    RegistroStatus,
    Clima,
    LadoPista,
)


def _is_password_hashed(password: str) -> bool:
    return password.startswith(("pbkdf2:", "scrypt:", "argon2:"))


def _prepare_password(password: str) -> str:
    if _is_password_hashed(password):
        return password
    return generate_password_hash(password)

class UsuarioRepository:
    @staticmethod
    def criar(
        db: Session,
        nome: str,
        email: str,
        senha: str,
        nivel_acesso: NivelAcesso = NivelAcesso.ENCARREGADO,
        telefone: str | None = None,
        telegram_thread_id: str | None = None,
    ) -> Usuario:
        usuario = Usuario(
            nome=nome,
            email=email,
            senha=_prepare_password(senha),
            telefone=telefone,
            nivel_acesso=nivel_acesso,
            telegram_thread_id=telegram_thread_id,
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        return usuario

    @staticmethod
    def criar_com_telegram(
        db: Session,
        nome: str,
        email: str,
        senha: str,
        telegram_chat_id: str,
        nivel_acesso: NivelAcesso = NivelAcesso.ENCARREGADO,
        telefone: str | None = None,
        telegram_thread_id: str | None = None,
    ) -> Usuario:
        usuario = Usuario(
            nome=nome,
            email=email,
            senha=_prepare_password(senha),
            telefone=telefone,
            telegram_chat_id=telegram_chat_id,
            telegram_thread_id=telegram_thread_id or telegram_chat_id,
            nivel_acesso=nivel_acesso,
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        return usuario

    @staticmethod
    def obter_por_id(db: Session, usuario_id: int) -> Usuario | None:
        return db.query(Usuario).filter(Usuario.id == usuario_id).first()

    @staticmethod
    def obter_por_email(db: Session, email: str) -> Usuario | None:
        return db.query(Usuario).filter(Usuario.email == email).first()

    @staticmethod
    def obter_por_telefone(db: Session, telefone: str) -> Usuario | None:
        return db.query(Usuario).filter(Usuario.telefone == telefone).first()

    @staticmethod
    def obter_por_telegram_chat_id(db: Session, chat_id: str) -> Usuario | None:
        return db.query(Usuario).filter(Usuario.telegram_chat_id == chat_id).first()

    @staticmethod
    def listar(db: Session) -> list[Usuario]:
        return db.query(Usuario).all()

    @staticmethod
    def atualizar(db: Session, usuario_id: int, **dados) -> Usuario | None:
        usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario:
            return None

        telefone_alterado = (
            "telefone" in dados
            and dados["telefone"] is not None
            and dados["telefone"] != usuario.telefone
        )

        if "senha" in dados and dados["senha"] is not None:
            dados["senha"] = _prepare_password(dados["senha"])

        for chave, valor in dados.items():
            if hasattr(usuario, chave) and valor is not None:
                setattr(usuario, chave, valor)

        if telefone_alterado:
            TelegramLinkCodeRepository.invalidar_ativos_por_usuario(db, usuario.id)

        db.commit()
        db.refresh(usuario)
        return usuario

    @staticmethod
    def deletar(db: Session, usuario_id: int) -> bool:
        usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario:
            return False
        db.delete(usuario)
        db.commit()
        return True

class FrenteServicoRepository:
    @staticmethod
    def criar(db: Session, nome: str, encarregado_responsavel: int | None = None, observacao: str | None = None) -> FrenteServico:
        frente = FrenteServico(nome=nome, encarregado_responsavel=encarregado_responsavel, observacao=observacao)
        db.add(frente)
        db.commit()
        db.refresh(frente)
        return frente

    @staticmethod
    def obter_por_id(db: Session, frente_id: int) -> FrenteServico | None:
        return db.query(FrenteServico).filter(FrenteServico.id == frente_id).first()

    @staticmethod
    def listar(db: Session) -> list[FrenteServico]:
        return db.query(FrenteServico).all()

    @staticmethod
    def atualizar(db: Session, frente_id: int, **dados) -> FrenteServico | None:
        frente = db.query(FrenteServico).filter(FrenteServico.id == frente_id).first()
        if not frente:
            return None
        for chave, valor in dados.items():
            if hasattr(frente, chave) and valor is not None:
                setattr(frente, chave, valor)
        db.commit()
        db.refresh(frente)
        return frente

    @staticmethod
    def deletar(db: Session, frente_id: int) -> bool:
        frente = db.query(FrenteServico).filter(FrenteServico.id == frente_id).first()
        if not frente:
            return False
        db.delete(frente)
        db.commit()
        return True

class RegistroRepository:
    @staticmethod
    def _required_missing_for_consolidated(payload: dict) -> list[str]:
        required_fields = [
            "data",
            "frente_servico_id",
            "usuario_registrador_id",
            "estaca_inicial",
            "estaca_final",
            "resultado",
            "tempo_manha",
            "tempo_tarde",
        ]
        return [field for field in required_fields if payload.get(field) in (None, "")]

    @staticmethod
    def criar(
        db: Session,
        frente_servico_id: int | None = None,
        data: date | None = None,
        usuario_registrador_id: int | None = None,
        estaca_inicial: float | None = None,
        estaca_final: float | None = None,
        resultado: float | None = None,
        tempo_manha: Clima | None = None,
        tempo_tarde: Clima | None = None,
        lado_pista: LadoPista | None = None,
        observacao: str | None = None,
        raw_text: str | None = None,
        source_message_id=None,
        status: RegistroStatus = RegistroStatus.PENDENTE,
    ) -> Registro:
        observacao_normalizada = (observacao or "").strip() or None

        if resultado is None and estaca_inicial is not None and estaca_final is not None:
            resultado = float(estaca_final) - float(estaca_inicial)

        payload = {
            "data": data,
            "frente_servico_id": frente_servico_id,
            "usuario_registrador_id": usuario_registrador_id,
            "estaca_inicial": estaca_inicial,
            "estaca_final": estaca_final,
            "resultado": resultado,
            "tempo_manha": tempo_manha,
            "tempo_tarde": tempo_tarde,
        }
        if status == RegistroStatus.CONSOLIDADO:
            missing = RegistroRepository._required_missing_for_consolidated(payload)
            if missing:
                raise ValueError(
                    "Nao e possivel marcar como consolidado sem campos basicos: " + ", ".join(missing)
                )

        registro = Registro(
            status=status,
            data=data,
            frente_servico_id=frente_servico_id,
            usuario_registrador_id=usuario_registrador_id,
            estaca_inicial=estaca_inicial,
            estaca_final=estaca_final,
            resultado=resultado,
            tempo_manha=tempo_manha,
            tempo_tarde=tempo_tarde,
            lado_pista=lado_pista,
            observacao=observacao_normalizada,
            raw_text=raw_text,
            source_message_id=source_message_id,
        )
        db.add(registro)
        db.commit()
        db.refresh(registro)
        return registro

    @staticmethod
    def obter_por_id(db: Session, registro_id: int) -> Registro | None:
        return db.query(Registro).filter(Registro.id == registro_id).first()

    @staticmethod
    def listar(db: Session) -> list[Registro]:
        return db.query(Registro).all()

    @staticmethod
    def listar_por_data(db: Session, data: date) -> list[Registro]:
        return db.query(Registro).filter(Registro.data == data).all()

    @staticmethod
    def listar_por_frente(db: Session, frente_servico_id: int) -> list[Registro]:
        return db.query(Registro).filter(Registro.frente_servico_id == frente_servico_id).all()

    @staticmethod
    def listar_por_usuario(db: Session, usuario_id: int) -> list[Registro]:
        return db.query(Registro).filter(Registro.usuario_registrador_id == usuario_id).all()

    @staticmethod
    def atualizar(db: Session, registro_id: int, **dados) -> Registro | None:
        registro = db.query(Registro).filter(Registro.id == registro_id).first()
        if not registro:
            return None
        if "pista" in dados and dados.get("lado_pista") is None:
            dados["lado_pista"] = dados.get("pista")
        for chave, valor in dados.items():
            if hasattr(registro, chave) and valor is not None:
                setattr(registro, chave, valor)

        if (
            dados.get("resultado") is None
            and registro.estaca_inicial is not None
            and registro.estaca_final is not None
        ):
            registro.resultado = float(registro.estaca_final) - float(registro.estaca_inicial)

        if registro.status == RegistroStatus.CONSOLIDADO:
            payload = {
                "data": registro.data,
                "frente_servico_id": registro.frente_servico_id,
                "usuario_registrador_id": registro.usuario_registrador_id,
                "estaca_inicial": registro.estaca_inicial,
                "estaca_final": registro.estaca_final,
                "resultado": registro.resultado,
                "tempo_manha": registro.tempo_manha,
                "tempo_tarde": registro.tempo_tarde,
            }
            missing = RegistroRepository._required_missing_for_consolidated(payload)
            if missing:
                raise ValueError(
                    "Registro consolidado ficou inconsistente. Campos ausentes: " + ", ".join(missing)
                )
        db.commit()
        db.refresh(registro)
        return registro

    @staticmethod
    def atualizar_status(db: Session, registro_id: int, status: RegistroStatus) -> Registro | None:
        registro = db.query(Registro).filter(Registro.id == registro_id).first()
        if not registro:
            return None

        if status == RegistroStatus.CONSOLIDADO:
            payload = {
                "data": registro.data,
                "frente_servico_id": registro.frente_servico_id,
                "usuario_registrador_id": registro.usuario_registrador_id,
                "estaca_inicial": registro.estaca_inicial,
                "estaca_final": registro.estaca_final,
                "resultado": registro.resultado,
                "tempo_manha": registro.tempo_manha,
                "tempo_tarde": registro.tempo_tarde,
            }
            missing = RegistroRepository._required_missing_for_consolidated(payload)
            if missing:
                raise ValueError(
                    "Nao e possivel consolidar registro sem campos basicos: " + ", ".join(missing)
                )

        registro.status = status
        db.commit()
        db.refresh(registro)
        return registro

    @staticmethod
    def deletar(db: Session, registro_id: int) -> bool:
        registro = db.query(Registro).filter(Registro.id == registro_id).first()
        if not registro:
            return False
        db.delete(registro)
        db.commit()
        return True


class RegistroImagemRepository:
    MAX_IMAGENS_POR_REGISTRO = 30

    @staticmethod
    def contar_por_registro(db: Session, registro_id: int) -> int:
        return db.query(RegistroImagem).filter(RegistroImagem.registro_id == registro_id).count()

    @staticmethod
    def listar_por_registro(db: Session, registro_id: int) -> list[RegistroImagem]:
        return (
            db.query(RegistroImagem)
            .filter(RegistroImagem.registro_id == registro_id)
            .order_by(RegistroImagem.created_at.asc())
            .all()
        )

    @staticmethod
    def obter_por_id(db: Session, imagem_id: int) -> RegistroImagem | None:
        return db.query(RegistroImagem).filter(RegistroImagem.id == imagem_id).first()

    @staticmethod
    def criar(
        db: Session,
        registro_id: int,
        *,
        storage_path: str | None = None,
        external_url: str | None = None,
        mime_type: str | None = None,
        file_size: int | None = None,
        origem: str = "api",
    ) -> RegistroImagem:
        if not storage_path and not external_url:
            raise ValueError("Informe storage_path ou external_url para salvar imagem do registro.")

        total = RegistroImagemRepository.contar_por_registro(db, registro_id)
        if total >= RegistroImagemRepository.MAX_IMAGENS_POR_REGISTRO:
            raise ValueError("Limite de 30 imagens por registro atingido.")

        item = RegistroImagem(
            registro_id=registro_id,
            storage_path=storage_path,
            external_url=external_url,
            mime_type=mime_type,
            file_size=file_size,
            origem=origem,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def deletar(db: Session, imagem_id: int) -> bool:
        item = db.query(RegistroImagem).filter(RegistroImagem.id == imagem_id).first()
        if not item:
            return False
        db.delete(item)
        db.commit()
        return True


class MensagemCampoRepository:
    @staticmethod
    def _obter_por_chave_natural(
        db: Session,
        *,
        telegram_chat_id: str,
        telegram_message_id: int,
    ) -> MensagemCampo | None:
        return (
            db.query(MensagemCampo)
            .filter(MensagemCampo.canal == CanalOrigemMensagem.TELEGRAM)
            .filter(MensagemCampo.telegram_chat_id == telegram_chat_id)
            .filter(MensagemCampo.telegram_message_id == telegram_message_id)
            .first()
        )

    @staticmethod
    def criar_telegram(
        db: Session,
        *,
        telegram_chat_id: str,
        telegram_message_id: int | None,
        telegram_update_id: int | None,
        texto_bruto: str | None,
        texto_normalizado: str | None,
        payload_json: str | None,
        hash_idempotencia: str,
        tipo_conteudo: ConteudoMensagemTipo,
        usuario_id: int | None = None,
    ) -> MensagemCampo:
        if telegram_message_id is not None:
            existente = MensagemCampoRepository._obter_por_chave_natural(
                db,
                telegram_chat_id=telegram_chat_id,
                telegram_message_id=telegram_message_id,
            )
            if existente:
                return existente

        existente = db.query(MensagemCampo).filter(MensagemCampo.hash_idempotencia == hash_idempotencia).first()
        if existente:
            return existente

        item = MensagemCampo(
            canal=CanalOrigemMensagem.TELEGRAM,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            telegram_update_id=telegram_update_id,
            usuario_id=usuario_id,
            tipo_conteudo=tipo_conteudo,
            texto_bruto=texto_bruto,
            texto_normalizado=texto_normalizado,
            payload_json=payload_json,
            hash_idempotencia=hash_idempotencia,
            status_processamento=ProcessamentoMensagemStatus.PENDENTE,
        )
        db.add(item)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if telegram_message_id is not None:
                existente = MensagemCampoRepository._obter_por_chave_natural(
                    db,
                    telegram_chat_id=telegram_chat_id,
                    telegram_message_id=telegram_message_id,
                )
                if existente:
                    return existente

            existente = db.query(MensagemCampo).filter(MensagemCampo.hash_idempotencia == hash_idempotencia).first()
            if existente:
                return existente
            raise
        db.refresh(item)
        return item

    @staticmethod
    def marcar_processada(db: Session, mensagem_id) -> None:
        item = db.query(MensagemCampo).filter(MensagemCampo.id == mensagem_id).first()
        if not item:
            return
        item.status_processamento = ProcessamentoMensagemStatus.PROCESSADA
        item.processada_em = datetime.utcnow()
        item.erro_processamento = None
        db.commit()

    @staticmethod
    def atualizar_usuario(db: Session, mensagem_id, usuario_id: int) -> None:
        item = db.query(MensagemCampo).filter(MensagemCampo.id == mensagem_id).first()
        if not item:
            return
        item.usuario_id = usuario_id
        db.commit()

    @staticmethod
    def marcar_erro(db: Session, mensagem_id, erro: str) -> None:
        item = db.query(MensagemCampo).filter(MensagemCampo.id == mensagem_id).first()
        if not item:
            return
        item.status_processamento = ProcessamentoMensagemStatus.ERRO
        item.erro_processamento = erro
        db.commit()

    @staticmethod
    def criar_agent_response(
        db: Session,
        *,
        telegram_chat_id: str,
        telegram_message_id: int,
        texto: str,
    ) -> MensagemCampo:
        """Persist an agent response message."""
        from backend.db.models import DirecaoMensagem
        
        item = MensagemCampo(
            canal=CanalOrigemMensagem.TELEGRAM,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            tipo_conteudo=ConteudoMensagemTipo.TEXTO,
            texto_bruto=texto,
            texto_normalizado=" ".join(str(texto or "").strip().split()) or None,
            direcao=DirecaoMensagem.AGENT,
            status_processamento=ProcessamentoMensagemStatus.PROCESSADA,
            processada_em=datetime.utcnow(),
            hash_idempotencia=f"agent:telegram:{telegram_chat_id}:{telegram_message_id}",
        )
        db.add(item)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(item)
        return item


class TelegramLinkCodeRepository:
    @staticmethod
    def criar(
        db: Session,
        user_id: int,
        code: str,
        expires_at: datetime,
        generated_by_user_id: int | None = None,
    ) -> TelegramLinkCode:
        item = TelegramLinkCode(
            user_id=user_id,
            code=code,
            generated_by_user_id=generated_by_user_id,
            expires_at=expires_at,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def obter_valido_por_codigo(db: Session, code: str) -> TelegramLinkCode | None:
        return (
            db.query(TelegramLinkCode)
            .filter(TelegramLinkCode.code == code)
            .filter(TelegramLinkCode.used_at.is_(None))
            .first()
        )

    @staticmethod
    def invalidar_ativos_por_usuario(db: Session, user_id: int) -> int:
        return (
            db.query(TelegramLinkCode)
            .filter(TelegramLinkCode.user_id == user_id)
            .filter(TelegramLinkCode.used_at.is_(None))
            .update({TelegramLinkCode.used_at: datetime.utcnow()}, synchronize_session=False)
        )

    @staticmethod
    def marcar_usado(db: Session, code_id: int) -> TelegramLinkCode | None:
        item = db.query(TelegramLinkCode).filter(TelegramLinkCode.id == code_id).first()
        if not item:
            return None
        item.used_at = datetime.utcnow()
        db.commit()
        db.refresh(item)
        return item

class Repository:
    usuarios = UsuarioRepository
    frentes_servico = FrenteServicoRepository
    registros = RegistroRepository
    registro_imagens = RegistroImagemRepository
    telegram_link_codes = TelegramLinkCodeRepository
    mensagens_campo = MensagemCampoRepository

