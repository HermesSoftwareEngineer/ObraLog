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
    RegistroSchema,
    TipoObra,
    UsuarioObra,
    TelegramLinkCode,
    MensagemCampo,
    Tenant,
    UserInviteCode,
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


def _resolve_tipo_obra(
    db: Session, tipo_obra_str: str | None, tipo_obra_id: int | None, tenant_id: int
) -> tuple[int | None, str | None]:
    """Resolve e sincroniza tipo_obra_id (FK) e tipo_obra (slug varchar)."""
    if tipo_obra_id:
        tipo = db.query(TipoObra).filter(
            TipoObra.id == tipo_obra_id, TipoObra.tenant_id == tenant_id
        ).first()
        slug = tipo.slug if tipo else (tipo_obra_str or "").strip() or None
        return tipo_obra_id, slug
    if tipo_obra_str:
        slug = tipo_obra_str.strip().lower()
        tipo = db.query(TipoObra).filter(
            TipoObra.slug == slug, TipoObra.tenant_id == tenant_id
        ).first()
        return (tipo.id if tipo else None), slug
    return None, None


class ObraRepository:
    @staticmethod
    def criar(
        db: Session,
        nome: str,
        codigo: str | None = None,
        descricao: str | None = None,
        ativo: bool = True,
        tipo_obra: str | None = None,
        tipo_obra_id: int | None = None,
        tenant_id: int | None = None,
    ) -> Obra:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        resolved_id, resolved_slug = _resolve_tipo_obra(db, tipo_obra, tipo_obra_id, tenant_id)
        obra = Obra(
            tenant_id=tenant_id,
            nome=(nome or "").strip(),
            codigo=(codigo or "").strip() or None,
            descricao=(descricao or "").strip() or None,
            ativo=bool(ativo),
            tipo_obra=resolved_slug,
            tipo_obra_id=resolved_id,
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

        tipo_obra_str = dados.pop("tipo_obra", None)
        tipo_obra_id = dados.pop("tipo_obra_id", None)
        if tipo_obra_str is not None or tipo_obra_id is not None:
            resolved_id, resolved_slug = _resolve_tipo_obra(db, tipo_obra_str, tipo_obra_id, tenant_id)
            obra.tipo_obra = resolved_slug
            obra.tipo_obra_id = resolved_id

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

_UNSET = object()


class FrenteServicoRepository:
    @staticmethod
    def criar(
        db: Session,
        nome: str,
        encarregado_responsavel: int | None = None,
        observacao: str | None = None,
        obra_id: int | None = None,
        registro_schema_id: int | None = None,
        tenant_id: int | None = None,
    ) -> FrenteServico:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        frente = FrenteServico(
            tenant_id=tenant_id,
            nome=nome,
            encarregado_responsavel=encarregado_responsavel,
            observacao=observacao,
            obra_id=obra_id,
            registro_schema_id=registro_schema_id,
        )
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
    def atualizar(
        db: Session,
        frente_id: int,
        tenant_id: int | None = None,
        obra_id: int | None = None,
        registro_schema_id=_UNSET,
        **dados,
    ) -> FrenteServico | None:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        frente = (
            db.query(FrenteServico)
            .filter(FrenteServico.tenant_id == tenant_id, FrenteServico.id == frente_id)
            .first()
        )
        if not frente:
            return None
        if obra_id is not None:
            frente.obra_id = obra_id
        if registro_schema_id is not _UNSET:
            frente.registro_schema_id = registro_schema_id
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
    def _resolve_location_type(payload: dict) -> str:
        metadata = payload.get("metadata_json") if isinstance(payload.get("metadata_json"), dict) else {}
        raw = (
            payload.get("tipo_localizacao")
            or metadata.get("tipo")
            or "estaca"
        )
        normalized = str(raw).strip().lower()
        if normalized == "text":
            return "texto"
        if normalized in {"estaca", "km", "texto"}:
            return normalized
        return "estaca"

    _SCHEMA_CAMPO_TO_ATTR: dict[str, str] = {
        "estaca_inicial": "estaca_inicial",
        "estaca_final": "estaca_final",
        "localizacao": "localizacao",
        "lado_pista": "lado_pista",
        "tempo_manha": "tempo_manha",
        "tempo_tarde": "tempo_tarde",
        "resultado": "resultado",
        "frente_servico": "frente_servico_id",
    }

    @staticmethod
    def _fetch_active_schema(db: Session, src, tenant_id: int) -> "RegistroSchema | None":
        """Fetch the active RegistroSchema for a registro or dict.

        Priority:
        1. registro_schema_id on the frente_servico (most specific)
        2. registro_schema_id stored on the registro (obra-level fallback)
        """
        def _get(field):
            return src.get(field) if isinstance(src, dict) else getattr(src, field, None)

        frente_id = _get("frente_servico_id")
        if frente_id:
            frente = db.query(FrenteServico).filter(
                FrenteServico.id == frente_id,
                FrenteServico.tenant_id == tenant_id,
            ).first()
            if frente and frente.registro_schema_id:
                schema = db.query(RegistroSchema).filter(
                    RegistroSchema.id == frente.registro_schema_id,
                    RegistroSchema.tenant_id == tenant_id,
                ).first()
                if schema:
                    return schema

        schema_id = _get("registro_schema_id")
        if schema_id:
            return db.query(RegistroSchema).filter(RegistroSchema.id == schema_id).first()

        return None

    @staticmethod
    def _missing_aprovado(src, schema: "RegistroSchema | None") -> list[str]:
        """Return missing required field names for aprovado status.
        src can be a Registro ORM instance or a plain dict."""
        def _get(field):
            return src.get(field) if isinstance(src, dict) else getattr(src, field, None)

        missing: list[str] = []
        if _get("data") in (None, ""):
            missing.append("data")
        if _get("usuario_registrador_id") in (None, ""):
            missing.append("usuario_registrador_id")

        campos = schema.campos_ativos if (schema and isinstance(getattr(schema, "campos_ativos", None), dict)) else None

        if campos is None:
            # Sem schema configurado — valida apenas campos universais
            if _get("frente_servico_id") in (None, ""):
                missing.append("frente_servico_id")
            return missing

        for campo, required in campos.items():
            if not required:
                continue
            attr = RegistroRepository._SCHEMA_CAMPO_TO_ATTR.get(campo)
            if attr is None:
                continue
            val = _get(attr)
            if campo == "resultado" and val in (None, ""):
                if _get("estaca_inicial") is not None and _get("estaca_final") is not None:
                    continue
            if val in (None, ""):
                missing.append(campo)

        return missing

    @staticmethod
    def _required_missing_for_consolidated(payload: dict) -> list[str]:
        required_common = [
            "data",
            "frente_servico_id",
            "usuario_registrador_id",
            "tempo_manha",
            "tempo_tarde",
        ]
        missing = [field for field in required_common if payload.get(field) in (None, "")]

        location_type = RegistroRepository._resolve_location_type(payload)
        if location_type == "texto":
            detail_text = payload.get("localizacao")
            if detail_text in (None, ""):
                missing.append("localizacao")
            return missing

        # For estaca/km profiles, start/end are required.
        for field in ("estaca_inicial", "estaca_final"):
            if payload.get(field) in (None, ""):
                missing.append(field)

        # resultado can be derived when both bounds are provided.
        if payload.get("resultado") in (None, ""):
            if payload.get("estaca_inicial") not in (None, "") and payload.get("estaca_final") not in (None, ""):
                try:
                    payload["resultado"] = float(payload["estaca_final"]) - float(payload["estaca_inicial"])
                except Exception:
                    missing.append("resultado")
            else:
                missing.append("resultado")

        return missing

    @staticmethod
    def criar(
        db: Session,
        obra_id: int | None = None,
        frente_servico_id: int | None = None,
        data: date | None = None,
        usuario_registrador_id: int | None = None,
        estaca_inicial: float | None = None,
        estaca_final: float | None = None,
        localizacao: str | None = None,
        metadata_json: dict | None = None,
        resultado: float | None = None,
        tempo_manha: Clima | None = None,
        tempo_tarde: Clima | None = None,
        lado_pista: LadoPista | None = None,
        observacao: str | None = None,
        raw_text: str | None = None,
        source_message_id=None,
        status: RegistroStatus = RegistroStatus.PENDENTE,
        registro_schema_id: int | None = None,
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
            "registro_schema_id": registro_schema_id,
            "frente_servico_id": frente_servico_id,
            "usuario_registrador_id": usuario_registrador_id,
            "estaca_inicial": estaca_inicial,
            "estaca_final": estaca_final,
            "localizacao": localizacao,
            "lado_pista": lado_pista,
            "resultado": resultado,
            "tempo_manha": tempo_manha,
            "tempo_tarde": tempo_tarde,
            "metadata_json": metadata_json,
        }
        if status == RegistroStatus.APROVADO:
            schema = RegistroRepository._fetch_active_schema(db, payload, tenant_id)
            missing = RegistroRepository._missing_aprovado(payload, schema)
            if missing:
                raise ValueError(
                    "Nao e possivel marcar como aprovado sem campos basicos: " + ", ".join(missing)
                )

        registro = Registro(
            tenant_id=tenant_id,
            status=status,
            data=data,
            obra_id=obra_id,
            frente_servico_id=frente_servico_id,
            usuario_registrador_id=usuario_registrador_id,
            registro_schema_id=registro_schema_id,
            estaca_inicial=estaca_inicial,
            estaca_final=estaca_final,
            localizacao=localizacao,
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
    def _limpar_extras_schema_anterior(
        db: Session, registro: "Registro", old_frente_id: int | None, tenant_id: int
    ) -> None:
        """Remove de metadata_json os campos_extras do schema antigo após troca de frente."""
        from sqlalchemy.orm.attributes import flag_modified
        if not old_frente_id or not isinstance(registro.metadata_json, dict):
            return
        old_frente = db.query(FrenteServico).filter(
            FrenteServico.id == old_frente_id,
            FrenteServico.tenant_id == tenant_id,
        ).first()
        if not old_frente or not old_frente.registro_schema_id:
            return
        old_schema = db.query(RegistroSchema).filter(
            RegistroSchema.id == old_frente.registro_schema_id,
            RegistroSchema.tenant_id == tenant_id,
        ).first()
        if not old_schema or not old_schema.campos_extras:
            return
        old_keys = {c["key"] for c in old_schema.campos_extras if c.get("key")}
        if not old_keys:
            return
        new_meta = {k: v for k, v in registro.metadata_json.items() if k not in old_keys}
        registro.metadata_json = new_meta if new_meta else None
        flag_modified(registro, "metadata_json")

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

        old_frente_id = registro.frente_servico_id

        if "pista" in dados and dados.get("lado_pista") is None:
            dados["lado_pista"] = dados.get("pista")
        for chave, valor in dados.items():
            if hasattr(registro, chave) and valor is not None:
                setattr(registro, chave, valor)

        new_frente_id = dados.get("frente_servico_id")
        if new_frente_id is not None and int(new_frente_id) != (old_frente_id or 0):
            RegistroRepository._limpar_extras_schema_anterior(db, registro, old_frente_id, tenant_id)

        if (
            dados.get("resultado") is None
            and registro.estaca_inicial is not None
            and registro.estaca_final is not None
        ):
            registro.resultado = float(registro.estaca_final) - float(registro.estaca_inicial)

        if registro.status == RegistroStatus.APROVADO:
            schema = RegistroRepository._fetch_active_schema(db, registro, tenant_id)
            missing = RegistroRepository._missing_aprovado(registro, schema)
            if missing:
                raise ValueError(
                    "Registro aprovado ficou inconsistente. Campos ausentes: " + ", ".join(missing)
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

        if status == RegistroStatus.APROVADO:
            schema = RegistroRepository._fetch_active_schema(db, registro, tenant_id)
            missing = RegistroRepository._missing_aprovado(registro, schema)
            if missing:
                raise ValueError(
                    "Nao e possivel aprovar registro sem campos basicos: " + ", ".join(missing)
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


    @staticmethod
    def criar_whatsapp(
        db: Session,
        tenant_id: int | None = None,
        *,
        chat_id: str,
        message_id: str,
        texto_bruto: str | None,
        texto_normalizado: str | None,
        payload_json: str | None,
        hash_idempotencia: str,
        tipo_conteudo: ConteudoMensagemTipo,
        usuario_id: int | None = None,
    ) -> MensagemCampo:
        tenant_id = _resolve_tenant_id(db, tenant_id)

        existente = db.query(MensagemCampo).filter(
            MensagemCampo.hash_idempotencia == hash_idempotencia
        ).first()
        if existente:
            return existente

        item = MensagemCampo(
            tenant_id=tenant_id,
            canal=CanalOrigemMensagem.WHATSAPP,
            telegram_chat_id=chat_id,
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
            existente = db.query(MensagemCampo).filter(
                MensagemCampo.hash_idempotencia == hash_idempotencia
            ).first()
            if existente:
                return existente
            raise
        db.refresh(item)
        return item

    @staticmethod
    def criar_agent_response_whatsapp(
        db: Session,
        tenant_id: int | None = None,
        *,
        chat_id: str,
        message_id: str,
        texto: str,
    ) -> MensagemCampo:
        from backend.db.models import DirecaoMensagem
        tenant_id = _resolve_tenant_id(db, tenant_id)
        item = MensagemCampo(
            tenant_id=tenant_id,
            canal=CanalOrigemMensagem.WHATSAPP,
            telegram_chat_id=chat_id,
            tipo_conteudo=ConteudoMensagemTipo.TEXTO,
            texto_bruto=texto,
            texto_normalizado=" ".join(str(texto or "").strip().split()) or None,
            direcao=DirecaoMensagem.AGENT,
            status_processamento=ProcessamentoMensagemStatus.PROCESSADA,
            processada_em=datetime.utcnow(),
            hash_idempotencia=f"agent:whatsapp:{chat_id}:{message_id}",
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

# ---------------------------------------------------------------------------
# UserInviteCodeRepository
# ---------------------------------------------------------------------------

class UserInviteCodeRepository:
    @staticmethod
    def criar(
        db: Session,
        tenant_id: int,
        criado_por: int,
        codigo: str,
        expira_em: datetime,
        nivel_acesso: str = "encarregado",
        email_destinatario: str | None = None,
    ) -> UserInviteCode:
        invite = UserInviteCode(
            tenant_id=tenant_id,
            criado_por=criado_por,
            codigo=codigo,
            expira_em=expira_em,
            nivel_acesso=nivel_acesso,
            email_destinatario=email_destinatario,
            ativo=True,
        )
        db.add(invite)
        db.commit()
        db.refresh(invite)
        return invite

    @staticmethod
    def obter_por_codigo(db: Session, codigo: str) -> UserInviteCode | None:
        return db.query(UserInviteCode).filter(UserInviteCode.codigo == codigo).first()

    @staticmethod
    def listar_por_tenant(db: Session, tenant_id: int, apenas_ativos: bool = True) -> list[UserInviteCode]:
        q = db.query(UserInviteCode).filter(UserInviteCode.tenant_id == tenant_id)
        if apenas_ativos:
            q = q.filter(UserInviteCode.ativo.is_(True), UserInviteCode.usado_em.is_(None))
        return q.order_by(UserInviteCode.created_at.desc()).all()

    @staticmethod
    def marcar_usado(db: Session, invite: UserInviteCode, usado_por: int) -> UserInviteCode:
        invite.usado_em = datetime.utcnow()
        invite.usado_por = usado_por
        invite.ativo = False
        db.commit()
        db.refresh(invite)
        return invite

    @staticmethod
    def cancelar(db: Session, codigo: str, tenant_id: int) -> bool:
        invite = (
            db.query(UserInviteCode)
            .filter(UserInviteCode.codigo == codigo, UserInviteCode.tenant_id == tenant_id)
            .first()
        )
        if not invite:
            return False
        invite.ativo = False
        db.commit()
        return True


class TipoObraRepository:
    @staticmethod
    def listar(db: Session, tenant_id: int, apenas_ativos: bool = True) -> list[TipoObra]:
        q = db.query(TipoObra).filter(TipoObra.tenant_id == tenant_id)
        if apenas_ativos:
            q = q.filter(TipoObra.ativo.is_(True))
        return q.order_by(TipoObra.nome).all()

    @staticmethod
    def obter_por_id(db: Session, tipo_obra_id: int, tenant_id: int) -> TipoObra | None:
        return (
            db.query(TipoObra)
            .filter(TipoObra.id == tipo_obra_id, TipoObra.tenant_id == tenant_id)
            .first()
        )

    @staticmethod
    def obter_por_slug(db: Session, slug: str, tenant_id: int) -> TipoObra | None:
        return (
            db.query(TipoObra)
            .filter(TipoObra.slug == slug.strip().lower(), TipoObra.tenant_id == tenant_id)
            .first()
        )

    @staticmethod
    def criar(
        db: Session,
        tenant_id: int,
        slug: str,
        nome: str,
        descricao: str | None = None,
        ativo: bool = True,
    ) -> TipoObra:
        tipo = TipoObra(
            tenant_id=tenant_id,
            slug=slug.strip().lower(),
            nome=nome.strip(),
            descricao=(descricao or "").strip() or None,
            ativo=ativo,
        )
        db.add(tipo)
        db.commit()
        db.refresh(tipo)
        return tipo

    @staticmethod
    def atualizar(db: Session, tipo_obra_id: int, tenant_id: int, **kwargs) -> TipoObra | None:
        tipo = TipoObraRepository.obter_por_id(db, tipo_obra_id, tenant_id)
        if not tipo:
            return None
        for key, value in kwargs.items():
            if hasattr(tipo, key):
                setattr(tipo, key, value)
        db.commit()
        db.refresh(tipo)
        return tipo

    @staticmethod
    def seed_defaults(db: Session, tenant_id: int) -> None:
        defaults = [
            ("rodovia",   "Rodovia",   "Obras de construção e manutenção de rodovias"),
            ("edificacao","Edificação", "Obras de construção civil e edificações"),
        ]
        for slug, nome, descricao in defaults:
            if not TipoObraRepository.obter_por_slug(db, slug, tenant_id):
                TipoObraRepository.criar(db, tenant_id, slug, nome, descricao)


class RegistroSchemaRepository:
    @staticmethod
    def obter_por_id(db: Session, schema_id: int, tenant_id: int | None = None) -> RegistroSchema | None:
        tenant_id = _resolve_tenant_id(db, tenant_id)
        return (
            db.query(RegistroSchema)
            .filter(RegistroSchema.tenant_id == tenant_id, RegistroSchema.id == schema_id)
            .first()
        )

    @staticmethod
    def listar(db: Session, tenant_id: int) -> list[RegistroSchema]:
        return (
            db.query(RegistroSchema)
            .filter(RegistroSchema.tenant_id == tenant_id)
            .order_by(RegistroSchema.tipo_obra, RegistroSchema.id)
            .all()
        )

    @staticmethod
    def criar(
        db: Session,
        tenant_id: int,
        tipo_obra: str | None,
        nome: str,
        campos_ativos: dict,
        campos_extras: list,
        ativo: bool = True,
        tipo_obra_id: int | None = None,
    ) -> RegistroSchema:
        schema = RegistroSchema(
            tenant_id=tenant_id,
            tipo_obra=(tipo_obra or "").strip() or None,
            tipo_obra_id=tipo_obra_id,
            nome=nome.strip(),
            campos_ativos=campos_ativos,
            campos_extras=campos_extras,
            ativo=ativo,
        )
        db.add(schema)
        db.commit()
        db.refresh(schema)
        return schema

    @staticmethod
    def atualizar(db: Session, schema_id: int, tenant_id: int, **kwargs) -> RegistroSchema | None:
        from sqlalchemy.orm.attributes import flag_modified

        schema = RegistroSchemaRepository.obter_por_id(db, schema_id, tenant_id)
        if not schema:
            return None
        for key, value in kwargs.items():
            if hasattr(schema, key):
                setattr(schema, key, value)
                if key in ("campos_ativos", "campos_extras"):
                    flag_modified(schema, key)
        db.commit()
        db.refresh(schema)
        return schema

    @staticmethod
    def deletar(db: Session, schema_id: int, tenant_id: int) -> bool:
        schema = RegistroSchemaRepository.obter_por_id(db, schema_id, tenant_id)
        if not schema:
            return False
        db.delete(schema)
        db.commit()
        return True

    @staticmethod
    def obter_ativo_por_tipo_obra(db: Session, tipo_obra: str, tenant_id: int) -> RegistroSchema | None:
        return (
            db.query(RegistroSchema)
            .filter(
                RegistroSchema.tenant_id == tenant_id,
                RegistroSchema.tipo_obra == tipo_obra,
                RegistroSchema.ativo.is_(True),
            )
            .first()
        )

    @staticmethod
    def obter_ativo_por_tipo_obra_id(db: Session, tipo_obra_id: int, tenant_id: int) -> RegistroSchema | None:
        return (
            db.query(RegistroSchema)
            .filter(
                RegistroSchema.tenant_id == tenant_id,
                RegistroSchema.tipo_obra_id == tipo_obra_id,
                RegistroSchema.ativo.is_(True),
            )
            .first()
        )

    @staticmethod
    def obter_ativo_para_obra(db: Session, obra_id: int, tenant_id: int) -> RegistroSchema | None:
        obra = ObraRepository.obter_por_id(db, obra_id, tenant_id=tenant_id)
        if not obra:
            return None
        if obra.tipo_obra_id:
            return RegistroSchemaRepository.obter_ativo_por_tipo_obra_id(db, obra.tipo_obra_id, tenant_id)
        if obra.tipo_obra:
            return RegistroSchemaRepository.obter_ativo_por_tipo_obra(db, obra.tipo_obra, tenant_id)
        return None

    @staticmethod
    def obter_para_frente(db: Session, frente_id: int, tenant_id: int) -> RegistroSchema | None:
        frente = (
            db.query(FrenteServico)
            .filter(FrenteServico.id == frente_id, FrenteServico.tenant_id == tenant_id)
            .first()
        )
        if not frente or not frente.registro_schema_id:
            return None
        return (
            db.query(RegistroSchema)
            .filter(
                RegistroSchema.id == frente.registro_schema_id,
                RegistroSchema.tenant_id == tenant_id,
            )
            .first()
        )


class UsuarioObraRepository:
    @staticmethod
    def listar_obras_do_usuario(db: Session, usuario_id: int, tenant_id: int) -> list[dict]:
        rows = (
            db.query(UsuarioObra, Obra)
            .join(Obra, Obra.id == UsuarioObra.obra_id)
            .filter(
                UsuarioObra.usuario_id == usuario_id,
                UsuarioObra.tenant_id == tenant_id,
            )
            .all()
        )
        return [
            {
                "id": obra.id,
                "nome": obra.nome,
                "tipo_obra": obra.tipo_obra,
                "eh_padrao": uo.eh_padrao,
                "ativo": uo.ativo,
            }
            for uo, obra in rows
        ]


class Repository:
    usuarios = UsuarioRepository
    obras = ObraRepository
    frentes_servico = FrenteServicoRepository
    registros = RegistroRepository
    registro_imagens = RegistroImagemRepository
    registro_schemas = RegistroSchemaRepository
    tipos_obra = TipoObraRepository
    usuario_obras = UsuarioObraRepository
    telegram_link_codes = TelegramLinkCodeRepository
    mensagens_campo = MensagemCampoRepository
    tenants = TenantRepository
    user_invite_codes = UserInviteCodeRepository

