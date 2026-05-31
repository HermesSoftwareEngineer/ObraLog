from langchain_core.tools import tool

from backend.db.repository import Repository
from backend.db.session import SessionLocal

from .common import assert_permission, to_dict


def build_frentes_servico_tools(actor_user_id: int, actor_level: str, tenant_id: int | None = None) -> list:
    del actor_user_id

    @tool
    def criar_frente_servico(
        nome: str,
        encarregado_responsavel: int | None = None,
        observacao: str | None = None,
        obra_id: int | None = None,
        registro_schema_id: int | None = None,
    ) -> dict:
        """Cria frente de serviço. Administrador e gerente."""
        assert_permission(actor_level, "create", "frentes_servico")
        with SessionLocal() as db:
            frente = Repository.frentes_servico.criar(
                db,
                nome,
                encarregado_responsavel,
                observacao,
                obra_id=obra_id,
                registro_schema_id=registro_schema_id,
                tenant_id=tenant_id,
            )
            return to_dict(frente)

    @tool
    def obter_frente_servico(frente_id: int | None = None, nome: str | None = None) -> dict:
        """Obtém uma frente de serviço pelo ID numérico ou pelo nome."""
        assert_permission(actor_level, "read", "frentes_servico")
        with SessionLocal() as db:
            if frente_id is not None:
                frente = Repository.frentes_servico.obter_por_id(db, frente_id, tenant_id=tenant_id)
            elif nome:
                from .common import normalize_text
                alvo = normalize_text(nome)
                todas = Repository.frentes_servico.listar(db, tenant_id=tenant_id)
                exatos = [f for f in todas if normalize_text(f.nome) == alvo]
                parciais = [f for f in todas if alvo in normalize_text(f.nome)]
                candidatos = exatos or parciais
                if len(candidatos) == 1:
                    frente = candidatos[0]
                elif len(candidatos) > 1:
                    return {
                        "ok": False,
                        "message": "Mais de uma frente encontrada. Seja mais específico.",
                        "opcoes": [f.nome for f in candidatos[:8]],
                    }
                else:
                    frente = None
            else:
                raise ValueError("Informe frente_id ou nome para identificar a frente de serviço.")
            if not frente:
                return {"ok": False, "message": "Frente de serviço não encontrada."}
            return {"ok": True, "frente_servico": to_dict(frente)}

    @tool
    def listar_frentes_servico() -> list[dict]:
        """Lista frentes de serviço para apoiar decisões e preencher cadastro de registros sem pedir ID ao usuário."""
        assert_permission(actor_level, "read", "frentes_servico")
        with SessionLocal() as db:
            frentes = Repository.frentes_servico.listar(db, tenant_id=tenant_id)
            return [to_dict(item) for item in frentes]

    @tool
    def atualizar_frente_servico(
        frente_id: int,
        nome: str | None = None,
        encarregado_responsavel: int | None = None,
        observacao: str | None = None,
        obra_id: int | None = None,
        registro_schema_id: int | None = None,
    ) -> dict:
        """Atualiza frente de serviço. Administrador e gerente."""
        assert_permission(actor_level, "update", "frentes_servico")
        with SessionLocal() as db:
            frente = Repository.frentes_servico.atualizar(
                db,
                frente_id,
                tenant_id=tenant_id,
                nome=nome,
                encarregado_responsavel=encarregado_responsavel,
                observacao=observacao,
                obra_id=obra_id,
                registro_schema_id=registro_schema_id,
            )
            if not frente:
                return {"ok": False, "message": "Frente de serviço não encontrada."}
            return {"ok": True, "frente_servico": to_dict(frente)}

    @tool
    def deletar_frente_servico(frente_id: int) -> dict:
        """Deleta frente de serviço. Administrador e gerente."""
        assert_permission(actor_level, "delete", "frentes_servico")
        with SessionLocal() as db:
            ok = Repository.frentes_servico.deletar(db, frente_id, tenant_id=tenant_id)
            return {"ok": ok}

    return [criar_frente_servico, obter_frente_servico, listar_frentes_servico, atualizar_frente_servico, deletar_frente_servico]
