from langchain_core.tools import tool

from backend.db.models import RegistroAuditoria
from backend.db.repository import Repository
from backend.db.session import SessionLocal

from .common import assert_permission, to_dict


def build_registro_auditoria_tools(actor_user_id: int, actor_level: str) -> list:
    del actor_user_id

    @tool
    def listar_auditoria_registro(registro_id: int, limit: int = 100) -> dict:
        """Lista trilha de auditoria de um registro do diário."""
        assert_permission(actor_level, "read", "registros")
        with SessionLocal() as db:
            registro = Repository.registros.obter_por_id(db, registro_id)
            if not registro:
                return {"ok": False, "message": "Registro não encontrado."}

            safe_limit = max(1, min(int(limit), 500))
            items = (
                db.query(RegistroAuditoria)
                .filter(RegistroAuditoria.registro_id == registro_id)
                .order_by(RegistroAuditoria.created_at.desc())
                .limit(safe_limit)
                .all()
            )
            return {"ok": True, "total": len(items), "items": [to_dict(item) for item in items]}

    return [listar_auditoria_registro]
