from datetime import date, datetime, time
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from backend.db.models import (
    Usuario,
    Obra,
    FrenteServico,
    Registro,
    RegistroImagem,
    TelegramLinkCode,
    MensagemCampo,
    Tenant,
    NivelAcesso,
    CanalOrigemMensagem,
    ConteudoMensagemTipo,
    ProcessamentoMensagemStatus,
    RegistroStatus,
    Clima,
    LadoPista,
)

# ---------------------------------------------------------------------------
# TenantRepository
# ---------------------------------------------------------------------------

class TenantRepository:
    @staticmethod
    def criar(
        db: Session,
        nome: str,
        slug: str,
        tipo_negocio: str | None = None,
        ativo: bool = True,
    ) -> Tenant:
        tenant = Tenant(nome=nome, slug=slug, tipo_negocio=tipo_negocio, ativo=ativo)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        return tenant

    @staticmethod
    def obter_por_id(db: Session, tenant_id: int) -> Tenant | None:
        return db.query(Tenant).filter(Tenant.id == tenant_id).first()

    @staticmethod
    def obter_por_slug(db: Session, slug: str) -> Tenant | None:
        return db.query(Tenant).filter(Tenant.slug == slug).first()

    @staticmethod
    def listar(db: Session) -> list[Tenant]:
        return db.query(Tenant).all()

    @staticmethod
    def get_default(db: Session) -> Tenant:
        """Return the default tenant, raising if it does not exist."""
        tenant = db.query(Tenant).filter(Tenant.slug == "default").first()
        if not tenant:
            raise RuntimeError("Default tenant not found – run migrations first.")
        return tenant


class ObraRepository:
    @staticmethod
    def criar(
        db: Session,
        nome: str,
        codigo: str | None = None,
        descricao: str | None = None,
        ativo: bool = True,
        tenant_id: int | None = None,
    ) -> Obra:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        obra = Obra(
            tenant_id=tenant_id,
            nome=(nome or "").strip(),
            codigo=(codigo or "").strip() or None,
            descricao=(descricao or "").strip() or None,
            ativo=bool(ativo),
        )
        db.add(obra)
        db.commit()
        db.refresh(obra)
        return obra

    @staticmethod
    def obter_por_id(db: Session, obra_id: int, tenant_id: int | None = None) -> Obra | None:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return (
            db.query(Obra)
            .filter(Obra.tenant_id == tenant_id, Obra.id == obra_id)
            .first()
        )

    @staticmethod
    def listar(db: Session, tenant_id: int | None = None) -> list[Obra]:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return db.query(Obra).filter(Obra.tenant_id == tenant_id).all()

    @staticmethod
    def atualizar(db: Session, obra_id: int, tenant_id: int | None = None, **dados) -> Obra | None:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        obra = (
            db.query(Obra)
            .filter(Obra.tenant_id == tenant_id, Obra.id == obra_id)
            .first()
        )
        if not obra:
            return None

        for chave, valor in dados.items():
            if hasattr(obra, chave) and valor is not None:
                setattr(obra, chave, valor)

        db.commit()
        db.refresh(obra)
        return obra

    @staticmethod
    def deletar(db: Session, obra_id: int, tenant_id: int | None = None) -> bool:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        obra = (
            db.query(Obra)
            .filter(Obra.tenant_id == tenant_id, Obra.id == obra_id)
            .first()
        )
        if not obra:
            return False
        db.delete(obra)
        db.commit()
        return True


def _is_password_hashed(password: str) -> bool:
    return password.startswith(("pbkdf2:", "scrypt:", "argon2:"))


def _prepare_password(password: str) -> str:
    if _is_password_hashed(password):
        return password
    return generate_password_hash(password)


def _resolve_tenant_id(db: Session, tenant_id: int | None) -> int:
    """Resolve effective tenant_id. Defaults to slug='default' for legacy call sites."""
    if tenant_id is not None:
        return tenant_id
    tenant = TenantRepository.get_default(db)
    return tenant.id

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
        tenant_id: int | None = None,
    ) -> Usuario:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        usuario = Usuario(
            tenant_id=tenant_id,
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
        tenant_id: int | None = None,
    ) -> Usuario:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        usuario = Usuario(
            tenant_id=tenant_id,
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
    def obter_por_id(db: Session, usuario_id: int, tenant_id: int | None = None) -> Usuario | None:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return (
            db.query(Usuario)
            .filter(Usuario.tenant_id == tenant_id, Usuario.id == usuario_id)
            .first()
        )

    @staticmethod
    def obter_por_email(db: Session, email: str, tenant_id: int | None = None) -> Usuario | None:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return (
            db.query(Usuario)
            .filter(Usuario.tenant_id == tenant_id, Usuario.email == email)
            .first()
        )

    @staticmethod
    def obter_por_telefone(db: Session, telefone: str, tenant_id: int | None = None) -> Usuario | None:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        # telefone is globally unique but we still scope by tenant to avoid cross-tenant leakage
        return (
            db.query(Usuario)
            .filter(Usuario.tenant_id == tenant_id, Usuario.telefone == telefone)
            .first()
        )

    @staticmethod
    def obter_por_telegram_chat_id(db: Session, chat_id: str) -> Usuario | None:
        # telegram_chat_id is globally unique – no tenant scope here intentionally
        # (one Telegram identity maps to one account across the system)
        return db.query(Usuario).filter(Usuario.telegram_chat_id == chat_id).first()

    @staticmethod
    def listar(db: Session, tenant_id: int | None = None) -> list[Usuario]:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return db.query(Usuario).filter(Usuario.tenant_id == tenant_id).all()

    @staticmethod
    def atualizar(db: Session, usuario_id: int, tenant_id: int | None = None, **dados) -> Usuario | None:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        usuario = (
            db.query(Usuario)
            .filter(Usuario.tenant_id == tenant_id, Usuario.id == usuario_id)
            .first()
        )
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
    def deletar(db: Session, usuario_id: int, tenant_id: int | None = None) -> bool:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        usuario = (
            db.query(Usuario)
            .filter(Usuario.tenant_id == tenant_id, Usuario.id == usuario_id)
            .first()
        )
        if not usuario:
            return False
        db.delete(usuario)
        db.commit()
        return True

class FrenteServicoRepository:
    @staticmethod
    def criar(db: Session, nome: str, encarregado_responsavel: int | None = None, observacao: str | None = None, tenant_id: int | None = None) -> FrenteServico:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        frente = FrenteServico(tenant_id=tenant_id, nome=nome, encarregado_responsavel=encarregado_responsavel, observacao=observacao)
        db.add(frente)
        db.commit()
        db.refresh(frente)
        return frente

    @staticmethod
    def obter_por_id(db: Session, frente_id: int, tenant_id: int | None = None) -> FrenteServico | None:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return (
            db.query(FrenteServico)
            .filter(FrenteServico.tenant_id == tenant_id, FrenteServico.id == frente_id)
            .first()
        )

    @staticmethod
    def listar(db: Session, tenant_id: int | None = None) -> list[FrenteServico]:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return db.query(FrenteServico).filter(FrenteServico.tenant_id == tenant_id).all()

    @staticmethod
    def atualizar(db: Session, frente_id: int, tenant_id: int | None = None, **dados) -> FrenteServico | None:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        frente = (
            db.query(FrenteServico)
            .filter(FrenteServico.tenant_id == tenant_id, FrenteServico.id == frente_id)
            .first()
        )
        if not frente:
            return None
        for chave, valor in dados.items():
            if hasattr(frente, chave) and valor is not None:
                setattr(frente, chave, valor)
        db.commit()
        db.refresh(frente)
        return frente

    @staticmethod
    def deletar(db: Session, frente_id: int, tenant_id: int | None = None) -> bool:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        frente = (
            db.query(FrenteServico)
            .filter(FrenteServico.tenant_id == tenant_id, FrenteServico.id == frente_id)
            .first()
        )
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
        obra_id: int | None = None,
        frente_servico_id: int | None = None,
        data: date | None = None,
        usuario_registrador_id: int | None = None,
        estaca_inicial: float | None = None,
        estaca_final: float | None = None,
        estaca: str | None = None,
        metadata_json: dict | None = None,
        resultado: float | None = None,
        tempo_manha: Clima | None = None,
        tempo_tarde: Clima | None = None,
        lado_pista: LadoPista | None = None,
        observacao: str | None = None,
        raw_text: str | None = None,
        source_message_id=None,
        status: RegistroStatus = RegistroStatus.PENDENTE,
        tenant_id: int | None = None,
    ) -> Registro:
        tenant_id = _resolve_tenant_id(db, tenant_id)

        if obra_id is not None:
            obra = ObraRepository.obter_por_id(db, int(obra_id), tenant_id=tenant_id)
            if not obra:
                raise ValueError("obra_id inválido para este tenant.")

        observacao_normalizada = (observacao or "").strip() or None

        if resultado is None and estaca_inicial is not None and estaca_final is not None:
            resultado = float(estaca_final) - float(estaca_inicial)

        payload = {
            "data": data,
            "obra_id": obra_id,
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
            tenant_id=tenant_id,
            status=status,
            data=data,
            obra_id=obra_id,
            frente_servico_id=frente_servico_id,
            usuario_registrador_id=usuario_registrador_id,
            estaca_inicial=estaca_inicial,
            estaca_final=estaca_final,
            estaca=estaca,
            metadata_json=metadata_json,
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
    def obter_por_id(db: Session, registro_id: int, tenant_id: int | None = None) -> Registro | None:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return (
            db.query(Registro)
            .filter(Registro.tenant_id == tenant_id, Registro.id == registro_id)
            .first()
        )

    @staticmethod
    def listar(db: Session, tenant_id: int | None = None) -> list[Registro]:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return db.query(Registro).filter(Registro.tenant_id == tenant_id).all()

    @staticmethod
    def listar_por_data(db: Session, data: date, tenant_id: int | None = None) -> list[Registro]:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return (
            db.query(Registro)
            .filter(Registro.tenant_id == tenant_id, Registro.data == data)
            .all()
        )

    @staticmethod
    def listar_por_frente(db: Session, frente_servico_id: int, tenant_id: int | None = None) -> list[Registro]:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return (
            db.query(Registro)
            .filter(Registro.tenant_id == tenant_id, Registro.frente_servico_id == frente_servico_id)
            .all()
        )

    @staticmethod
    def listar_por_obra(db: Session, obra_id: int, tenant_id: int | None = None) -> list[Registro]:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return (
            db.query(Registro)
            .filter(Registro.tenant_id == tenant_id, Registro.obra_id == obra_id)
            .all()
        )

    @staticmethod
    def listar_por_usuario(db: Session, usuario_id: int, tenant_id: int | None = None) -> list[Registro]:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return (
            db.query(Registro)
            .filter(Registro.tenant_id == tenant_id, Registro.usuario_registrador_id == usuario_id)
            .all()
        )

    @staticmethod
    def atualizar(db: Session, registro_id: int, tenant_id: int | None = None, **dados) -> Registro | None:
        tenant_id = _resolve_tenant_id(db, tenant_id)

        if "obra_id" in dados and dados.get("obra_id") is not None:
            obra = ObraRepository.obter_por_id(db, int(dados["obra_id"]), tenant_id=tenant_id)
            if not obra:
                raise ValueError("obra_id inválido para este tenant.")

        registro = (
            db.query(Registro)
            .filter(Registro.tenant_id == tenant_id, Registro.id == registro_id)
            .first()
        )
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
    def atualizar_status(db: Session, registro_id: int, status: RegistroStatus, tenant_id: int | None = None) -> Registro | None:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        registro = (
            db.query(Registro)
            .filter(Registro.tenant_id == tenant_id, Registro.id == registro_id)
            .first()
        )
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
    def deletar(db: Session, registro_id: int, tenant_id: int | None = None) -> bool:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        registro = (
            db.query(Registro)
            .filter(Registro.tenant_id == tenant_id, Registro.id == registro_id)
            .first()
        )
        if not registro:
            return False
        db.delete(registro)
        db.commit()
        return True


class RegistroImagemRepository:
    MAX_IMAGENS_POR_REGISTRO = 30

    @staticmethod
    def contar_por_registro(db: Session, registro_id: int, tenant_id: int | None = None) -> int:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return (
            db.query(RegistroImagem)
            .filter(RegistroImagem.tenant_id == tenant_id, RegistroImagem.registro_id == registro_id)
            .count()
        )

    @staticmethod
    def listar_por_registro(db: Session, registro_id: int, tenant_id: int | None = None) -> list[RegistroImagem]:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return (
            db.query(RegistroImagem)
            .filter(RegistroImagem.tenant_id == tenant_id, RegistroImagem.registro_id == registro_id)
            .order_by(RegistroImagem.created_at.asc())
            .all()
        )

    @staticmethod
    def obter_por_id(db: Session, imagem_id: int, tenant_id: int | None = None) -> RegistroImagem | None:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return (
            db.query(RegistroImagem)
            .filter(RegistroImagem.tenant_id == tenant_id, RegistroImagem.id == imagem_id)
            .first()
        )

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
        tenant_id: int | None = None,
    ) -> RegistroImagem:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        if not storage_path and not external_url:
            raise ValueError("Informe storage_path ou external_url para salvar imagem do registro.")

        total = RegistroImagemRepository.contar_por_registro(db, registro_id, tenant_id=tenant_id)
        if total >= RegistroImagemRepository.MAX_IMAGENS_POR_REGISTRO:
            raise ValueError("Limite de 30 imagens por registro atingido.")

        item = RegistroImagem(
            tenant_id=tenant_id,
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
    def deletar(db: Session, imagem_id: int, tenant_id: int | None = None) -> bool:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        item = (
            db.query(RegistroImagem)
            .filter(RegistroImagem.tenant_id == tenant_id, RegistroImagem.id == imagem_id)
            .first()
        )
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
        tenant_id: int | None,
        telegram_chat_id: str,
        telegram_message_id: int,
    ) -> MensagemCampo | None:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return (
            db.query(MensagemCampo)
            .filter(MensagemCampo.canal == CanalOrigemMensagem.TELEGRAM)
            .filter(MensagemCampo.tenant_id == tenant_id)
            .filter(MensagemCampo.telegram_chat_id == telegram_chat_id)
            .filter(MensagemCampo.telegram_message_id == telegram_message_id)
            .first()
        )

    @staticmethod
    def criar_telegram(
        db: Session,
        tenant_id: int | None = None,
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
        tenant_id = _resolve_tenant_id(db, tenant_id)
        if telegram_message_id is not None:
            existente = MensagemCampoRepository._obter_por_chave_natural(
                db,
                tenant_id=tenant_id,
                telegram_chat_id=telegram_chat_id,
                telegram_message_id=telegram_message_id,
            )
            if existente:
                return existente

        existente = db.query(MensagemCampo).filter(MensagemCampo.hash_idempotencia == hash_idempotencia).first()
        if existente:
            return existente

        item = MensagemCampo(
            tenant_id=tenant_id,
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
                    tenant_id=tenant_id,
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
        # tenant scope not required here: caller already holds the id from a prior scoped query
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
        tenant_id: int | None = None,
        *,
        telegram_chat_id: str,
        telegram_message_id: int,
        texto: str,
    ) -> MensagemCampo:
        """Persist an agent response message."""
        from backend.db.models import DirecaoMensagem
        tenant_id = _resolve_tenant_id(db, tenant_id)
        
        item = MensagemCampo(
            tenant_id=tenant_id,
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
        tenant_id: int | None = None,
    ) -> TelegramLinkCode:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        item = TelegramLinkCode(
            tenant_id=tenant_id,
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
    obras = ObraRepository
    frentes_servico = FrenteServicoRepository
    registros = RegistroRepository
    registro_imagens = RegistroImagemRepository
    telegram_link_codes = TelegramLinkCodeRepository
    mensagens_campo = MensagemCampoRepository
    tenants = TenantRepository

