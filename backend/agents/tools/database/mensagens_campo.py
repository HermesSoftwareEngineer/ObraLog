import json
from uuid import UUID

from langchain_core.tools import tool

from backend.db.models import MensagemCampo, ProcessamentoMensagemStatus
from backend.db.session import SessionLocal

from .common import assert_permission, to_dict


def build_mensagens_campo_tools(actor_user_id: int, actor_level: str, tenant_id: int | None = None) -> list:
    del actor_user_id

    @tool
    def listar_mensagens_campo(
        status: str | None = None,
        telegram_chat_id: str | None = None,
        limit: int = 50,
    ) -> dict:
        """Lista mensagens de campo capturadas, com filtros operacionais."""
        assert_permission(actor_level, "read", "registros")
        with SessionLocal() as db:
            query = db.query(MensagemCampo)
            if tenant_id is not None:
                query = query.filter(MensagemCampo.tenant_id == tenant_id)

            if status:
                try:
                    parsed_status = ProcessamentoMensagemStatus(status)
                except ValueError as exc:
                    raise ValueError("status inválido. Use: pendente, processada ou erro.") from exc
                query = query.filter(MensagemCampo.status_processamento == parsed_status)

            if telegram_chat_id:
                query = query.filter(MensagemCampo.telegram_chat_id == str(telegram_chat_id))

            safe_limit = max(1, min(int(limit), 200))
            items = query.order_by(MensagemCampo.recebida_em.desc()).limit(safe_limit).all()
            payload = []
            for item in items:
                data = to_dict(item)
                raw_payload = data.get("payload_json")
                if raw_payload:
                    try:
                        data["payload_json"] = json.loads(raw_payload)
                    except Exception:
                        pass
                payload.append(data)
            return {"ok": True, "total": len(payload), "items": payload}

    @tool
    def obter_mensagem_campo(mensagem_id: str) -> dict:
        """Obtém uma mensagem de campo específica por UUID."""
        assert_permission(actor_level, "read", "registros")
        try:
            parsed_id = UUID(str(mensagem_id))
        except Exception as exc:
            raise ValueError("mensagem_id inválido. Use UUID válido.") from exc

        with SessionLocal() as db:
            query = db.query(MensagemCampo).filter(MensagemCampo.id == parsed_id)
            if tenant_id is not None:
                query = query.filter(MensagemCampo.tenant_id == tenant_id)
            item = query.first()
            if not item:
                return {"ok": False, "message": "Mensagem de campo não encontrada."}
            data = to_dict(item)
            raw_payload = data.get("payload_json")
            if raw_payload:
                try:
                    data["payload_json"] = json.loads(raw_payload)
                except Exception:
                    pass
            return {"ok": True, "item": data}

    return [listar_mensagens_campo, obter_mensagem_campo]
