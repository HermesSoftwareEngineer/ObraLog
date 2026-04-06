from datetime import date
from decimal import Decimal
import unicodedata

from langchain_core.tools import tool

from backend.db.models import Clima, LadoPista, NivelAcesso
from backend.db.repository import Repository
from backend.db.session import SessionLocal


def _to_dict(obj):
    data = {}
    for key in obj.__table__.columns.keys():
        if key == "senha":
            continue
        value = getattr(obj, key)
        if isinstance(value, Decimal):
            data[key] = float(value)
        elif hasattr(value, "value"):
            data[key] = value.value
        else:
            data[key] = value
    return data


def _assert_permission(actor_level: str, operation: str, resource: str):
    rules = {
        NivelAcesso.ADMINISTRADOR.value: {
            "usuarios": {"create", "read", "update", "delete"},
            "frentes_servico": {"create", "read", "update", "delete"},
            "registros": {"create", "read", "update", "delete"},
        },
        NivelAcesso.GERENTE.value: {
            "usuarios": {"read"},
            "frentes_servico": {"create", "read", "update", "delete"},
            "registros": {"create", "read", "update", "delete"},
        },
        NivelAcesso.ENCARREGADO.value: {
            "usuarios": {"read"},
            "frentes_servico": {"read"},
            "registros": {"create", "read", "update", "delete"},
        },
    }

    allowed = rules.get(actor_level, {}).get(resource, set())
    if operation not in allowed:
        raise PermissionError(f"Acesso negado para {operation} em {resource} no nível {actor_level}.")


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.strip().lower().split())


def _parse_lado_pista(value: str | None) -> LadoPista | None:
    if not value:
        return None
    normalized = _normalize_text(value)
    aliases = {
        "direita": LadoPista.DIREITA,
        "lado direita": LadoPista.DIREITA,
        "lado direito": LadoPista.DIREITA,
        "dir": LadoPista.DIREITA,
        "esquerda": LadoPista.ESQUERDA,
        "lado esquerda": LadoPista.ESQUERDA,
        "lado esquerdo": LadoPista.ESQUERDA,
        "esq": LadoPista.ESQUERDA,
    }
    parsed = aliases.get(normalized)
    if parsed is None:
        raise ValueError("lado_pista inválido. Valores aceitos: direita, esquerda.")
    return parsed


def _parse_clima(value: str | None, field_name: str) -> Clima | None:
    if not value:
        return None
    normalized = _normalize_text(value)
    aliases = {
        "limpo": Clima.LIMPO,
        "sol": Clima.LIMPO,
        "ensolarado": Clima.LIMPO,
        "nublado": Clima.NUBLADO,
        "chuva": Clima.NUBLADO,
        "chuvoso": Clima.NUBLADO,
        "impraticavel": Clima.IMPRATICAVEL,
        "impraticavel total": Clima.IMPRATICAVEL,
    }
    parsed = aliases.get(normalized)
    if parsed is None:
        raise ValueError(f"{field_name} inválido. Valores aceitos: limpo, nublado, impraticavel.")
    return parsed


def _parse_nivel_acesso(value: str | None) -> NivelAcesso | None:
    if not value:
        return None
    normalized = _normalize_text(value)
    aliases = {
        "administrador": NivelAcesso.ADMINISTRADOR,
        "admin": NivelAcesso.ADMINISTRADOR,
        "gerente": NivelAcesso.GERENTE,
        "encarregado": NivelAcesso.ENCARREGADO,
    }
    parsed = aliases.get(normalized)
    if parsed is None:
        raise ValueError("nivel_acesso inválido. Valores aceitos: administrador, gerente, encarregado.")
    return parsed


def _build_tools(actor_user_id: int, actor_level: str):
    @tool
    def criar_usuario(
        nome: str,
        email: str,
        senha: str,
        nivel_acesso: str = "encarregado",
        telefone: str | None = None,
        telegram_chat_id: str | None = None,
    ) -> dict:
        """Cria um usuário. Apenas administrador."""
        _assert_permission(actor_level, "create", "usuarios")
        nivel = _parse_nivel_acesso(nivel_acesso) or NivelAcesso.ENCARREGADO
        with SessionLocal() as db:
            if telegram_chat_id:
                usuario = Repository.usuarios.criar_com_telegram(
                    db=db,
                    nome=nome,
                    email=email,
                    senha=senha,
                    telegram_chat_id=telegram_chat_id,
                    nivel_acesso=nivel,
                    telefone=telefone,
                )
            else:
                usuario = Repository.usuarios.criar(
                    db=db,
                    nome=nome,
                    email=email,
                    senha=senha,
                    nivel_acesso=nivel,
                    telefone=telefone,
                )
            return _to_dict(usuario)

    @tool
    def listar_usuarios() -> list[dict]:
        """Lista usuários. Administrador e gerente; encarregado vê apenas si próprio."""
        _assert_permission(actor_level, "read", "usuarios")
        with SessionLocal() as db:
            if actor_level == NivelAcesso.ENCARREGADO.value:
                usuario = Repository.usuarios.obter_por_id(db, actor_user_id)
                return [_to_dict(usuario)] if usuario else []
            usuarios = Repository.usuarios.listar(db)
            return [_to_dict(item) for item in usuarios]

    @tool
    def atualizar_usuario(
        usuario_id: int,
        nome: str | None = None,
        email: str | None = None,
        senha: str | None = None,
        nivel_acesso: str | None = None,
        telefone: str | None = None,
        telegram_chat_id: str | None = None,
    ) -> dict:
        """Atualiza um usuário. Apenas administrador."""
        _assert_permission(actor_level, "update", "usuarios")
        payload = {
            "nome": nome,
            "email": email,
            "senha": senha,
            "telefone": telefone,
            "telegram_chat_id": telegram_chat_id,
        }
        if nivel_acesso:
            payload["nivel_acesso"] = _parse_nivel_acesso(nivel_acesso)
        with SessionLocal() as db:
            usuario = Repository.usuarios.atualizar(db, usuario_id, **payload)
            if not usuario:
                return {"ok": False, "message": "Usuário não encontrado."}
            return {"ok": True, "usuario": _to_dict(usuario)}

    @tool
    def deletar_usuario(usuario_id: int) -> dict:
        """Deleta usuário. Apenas administrador."""
        _assert_permission(actor_level, "delete", "usuarios")
        with SessionLocal() as db:
            ok = Repository.usuarios.deletar(db, usuario_id)
            return {"ok": ok}

    @tool
    def criar_frente_servico(nome: str, encarregado_responsavel: int | None = None, observacao: str | None = None) -> dict:
        """Cria frente de serviço. Administrador e gerente."""
        _assert_permission(actor_level, "create", "frentes_servico")
        with SessionLocal() as db:
            frente = Repository.frentes_servico.criar(db, nome, encarregado_responsavel, observacao)
            return _to_dict(frente)

    @tool
    def listar_frentes_servico() -> list[dict]:
        """Lista frentes de serviço."""
        _assert_permission(actor_level, "read", "frentes_servico")
        with SessionLocal() as db:
            frentes = Repository.frentes_servico.listar(db)
            return [_to_dict(item) for item in frentes]

    @tool
    def atualizar_frente_servico(frente_id: int, nome: str | None = None, encarregado_responsavel: int | None = None, observacao: str | None = None) -> dict:
        """Atualiza frente de serviço. Administrador e gerente."""
        _assert_permission(actor_level, "update", "frentes_servico")
        with SessionLocal() as db:
            frente = Repository.frentes_servico.atualizar(
                db,
                frente_id,
                nome=nome,
                encarregado_responsavel=encarregado_responsavel,
                observacao=observacao,
            )
            if not frente:
                return {"ok": False, "message": "Frente de serviço não encontrada."}
            return {"ok": True, "frente_servico": _to_dict(frente)}

    @tool
    def deletar_frente_servico(frente_id: int) -> dict:
        """Deleta frente de serviço. Administrador e gerente."""
        _assert_permission(actor_level, "delete", "frentes_servico")
        with SessionLocal() as db:
            ok = Repository.frentes_servico.deletar(db, frente_id)
            return {"ok": ok}

    @tool
    def criar_registro(
        frente_servico_id: int,
        data_iso: str | None = None,
        estaca_inicial: float | None = None,
        estaca_final: float | None = None,
        tempo_manha: str | None = None,
        tempo_tarde: str | None = None,
        pista: str | None = None,
        lado_pista: str | None = None,
        observacao: str | None = None,
    ) -> dict:
        """Cria registro no diário de obra. Todos os níveis."""
        _assert_permission(actor_level, "create", "registros")
        data = None
        if data_iso:
            data = date.fromisoformat(data_iso)
        
        resultado = None
        if estaca_inicial is not None and estaca_final is not None:
            resultado = estaca_final - estaca_inicial

        with SessionLocal() as db:
            registro = Repository.registros.criar(
                db=db,
                data=data,
                frente_servico_id=frente_servico_id,
                usuario_registrador_id=actor_user_id,
                estaca_inicial=estaca_inicial,
                estaca_final=estaca_final,
                resultado=resultado,
                tempo_manha=_parse_clima(tempo_manha, "tempo_manha"),
                tempo_tarde=_parse_clima(tempo_tarde, "tempo_tarde"),
                pista=_parse_lado_pista(pista),
                lado_pista=_parse_lado_pista(lado_pista),
                observacao=observacao,
            )
            return _to_dict(registro)

    @tool
    def listar_registros(data_iso: str | None = None, frente_servico_id: int | None = None, usuario_id: int | None = None) -> list[dict]:
        """Lista registros com filtros opcionais."""
        _assert_permission(actor_level, "read", "registros")
        with SessionLocal() as db:
            if actor_level == NivelAcesso.ENCARREGADO.value:
                registros = Repository.registros.listar_por_usuario(db, actor_user_id)
            elif data_iso:
                registros = Repository.registros.listar_por_data(db, date.fromisoformat(data_iso))
            elif frente_servico_id:
                registros = Repository.registros.listar_por_frente(db, frente_servico_id)
            elif usuario_id:
                registros = Repository.registros.listar_por_usuario(db, usuario_id)
            else:
                registros = Repository.registros.listar(db)
            return [_to_dict(item) for item in registros]

    @tool
    def atualizar_registro(
        registro_id: int,
        data_iso: str | None = None,
        frente_servico_id: int | None = None,
        usuario_registrador_id: int | None = None,
        estaca_inicial: float | None = None,
        estaca_final: float | None = None,
        resultado: float | None = None,
        tempo_manha: str | None = None,
        tempo_tarde: str | None = None,
        pista: str | None = None,
        lado_pista: str | None = None,
        observacao: str | None = None,
    ) -> dict:
        """Atualiza registro do diário."""
        _assert_permission(actor_level, "update", "registros")
        payload = {
            "frente_servico_id": frente_servico_id,
            "usuario_registrador_id": usuario_registrador_id,
            "estaca_inicial": estaca_inicial,
            "estaca_final": estaca_final,
            "resultado": resultado,
            "tempo_manha": _parse_clima(tempo_manha, "tempo_manha"),
            "tempo_tarde": _parse_clima(tempo_tarde, "tempo_tarde"),
            "pista": _parse_lado_pista(pista),
            "lado_pista": _parse_lado_pista(lado_pista),
            "observacao": observacao,
        }
        if data_iso:
            payload["data"] = date.fromisoformat(data_iso)

        if estaca_inicial is not None and estaca_final is not None and resultado is None:
            payload["resultado"] = estaca_final - estaca_inicial

        with SessionLocal() as db:
            registro = Repository.registros.obter_por_id(db, registro_id)
            if not registro:
                return {"ok": False, "message": "Registro não encontrado."}
            if actor_level == NivelAcesso.ENCARREGADO.value and registro.usuario_registrador_id != actor_user_id:
                raise PermissionError("Encarregado só pode atualizar seus próprios registros.")
            updated = Repository.registros.atualizar(db, registro_id, **payload)
            return {"ok": True, "registro": _to_dict(updated)}

    @tool
    def deletar_registro(registro_id: int) -> dict:
        """Deleta registro do diário."""
        _assert_permission(actor_level, "delete", "registros")
        with SessionLocal() as db:
            registro = Repository.registros.obter_por_id(db, registro_id)
            if not registro:
                return {"ok": False, "message": "Registro não encontrado."}
            if actor_level == NivelAcesso.ENCARREGADO.value and registro.usuario_registrador_id != actor_user_id:
                raise PermissionError("Encarregado só pode deletar seus próprios registros.")
            ok = Repository.registros.deletar(db, registro_id)
            return {"ok": ok}

    return [
        criar_usuario,
        listar_usuarios,
        atualizar_usuario,
        deletar_usuario,
        criar_frente_servico,
        listar_frentes_servico,
        atualizar_frente_servico,
        deletar_frente_servico,
        criar_registro,
        listar_registros,
        atualizar_registro,
        deletar_registro,
    ]


def get_database_tools(actor_user_id: int, actor_level: str):
    return _build_tools(actor_user_id=actor_user_id, actor_level=actor_level)
