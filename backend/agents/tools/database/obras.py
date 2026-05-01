from langchain_core.tools import tool

from backend.db.repository import Repository
from backend.db.session import SessionLocal

from .common import assert_permission, to_dict


def build_obras_tools(actor_user_id: int, actor_level: str, tenant_id: int | None = None) -> list:
    del actor_user_id

    @tool
    def criar_obra(nome: str, codigo: str | None = None, descricao: str | None = None, ativo: bool = True) -> dict:
        """Cria obra para vinculação em registros e alertas."""
        assert_permission(actor_level, "create", "frentes_servico")
        with SessionLocal() as db:
            obra = Repository.obras.criar(
                db,
                nome=nome,
                codigo=codigo,
                descricao=descricao,
                ativo=bool(ativo),
                tenant_id=tenant_id,
            )
            return to_dict(obra)

    @tool
    def listar_obras() -> list[dict]:
        """Lista obras disponíveis no tenant atual."""
        assert_permission(actor_level, "read", "frentes_servico")
        with SessionLocal() as db:
            obras = Repository.obras.listar(db, tenant_id=tenant_id)
            return [to_dict(item) for item in obras]

    @tool
    def atualizar_obra(
        obra_id: int,
        nome: str | None = None,
        codigo: str | None = None,
        descricao: str | None = None,
        ativo: bool | None = None,
    ) -> dict:
        """Atualiza metadados de obra."""
        assert_permission(actor_level, "update", "frentes_servico")
        with SessionLocal() as db:
            obra = Repository.obras.atualizar(
                db,
                obra_id,
                tenant_id=tenant_id,
                nome=nome,
                codigo=codigo,
                descricao=descricao,
                ativo=ativo,
            )
            if not obra:
                return {"ok": False, "message": "Obra não encontrada."}
            return {"ok": True, "obra": to_dict(obra)}

    @tool
    def deletar_obra(obra_id: int) -> dict:
        """Remove obra."""
        assert_permission(actor_level, "delete", "frentes_servico")
        with SessionLocal() as db:
            ok = Repository.obras.deletar(db, obra_id, tenant_id=tenant_id)
            return {"ok": ok}

    return [criar_obra, listar_obras, atualizar_obra, deletar_obra]
