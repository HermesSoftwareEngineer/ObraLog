from langchain_core.tools import tool

from backend.db.models import NivelAcesso
from backend.db.repository import Repository
from backend.db.session import SessionLocal

from .common import assert_permission, parse_nivel_acesso, to_dict


def build_usuarios_tools(actor_user_id: int, actor_level: str) -> list:
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
        assert_permission(actor_level, "create", "usuarios")
        nivel = parse_nivel_acesso(nivel_acesso) or NivelAcesso.ENCARREGADO
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
            return to_dict(usuario)

    @tool
    def listar_usuarios() -> list[dict]:
        """Lista usuários. Administrador e gerente; encarregado vê apenas si próprio."""
        assert_permission(actor_level, "read", "usuarios")
        with SessionLocal() as db:
            if actor_level == NivelAcesso.ENCARREGADO.value:
                usuario = Repository.usuarios.obter_por_id(db, actor_user_id)
                return [to_dict(usuario)] if usuario else []
            usuarios = Repository.usuarios.listar(db)
            return [to_dict(item) for item in usuarios]

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
        assert_permission(actor_level, "update", "usuarios")
        payload = {
            "nome": nome,
            "email": email,
            "senha": senha,
            "telefone": telefone,
            "telegram_chat_id": telegram_chat_id,
        }
        if nivel_acesso:
            payload["nivel_acesso"] = parse_nivel_acesso(nivel_acesso)
        with SessionLocal() as db:
            usuario = Repository.usuarios.atualizar(db, usuario_id, **payload)
            if not usuario:
                return {"ok": False, "message": "Usuário não encontrado."}
            return {"ok": True, "usuario": to_dict(usuario)}

    @tool
    def deletar_usuario(usuario_id: int) -> dict:
        """Deleta usuário. Apenas administrador."""
        assert_permission(actor_level, "delete", "usuarios")
        with SessionLocal() as db:
            ok = Repository.usuarios.deletar(db, usuario_id)
            return {"ok": ok}

    return [criar_usuario, listar_usuarios, atualizar_usuario, deletar_usuario]
