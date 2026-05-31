"""Shared utilities for agent nodes: tool resolution, context extraction, output normalization."""
import os
import unicodedata
import logging

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

try:
    from ..tools import get_database_tools, get_gateway_tools, get_telegram_tools
    from ..gateway.rag_service import BusinessRAGService
except ImportError:
    from tools import get_database_tools, get_gateway_tools, get_telegram_tools  # type: ignore
    from gateway.rag_service import BusinessRAGService  # type: ignore

logger = logging.getLogger("obralog.agent.tool_utils")


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().strip().split())


def last_human_text(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        return item["text"]
    return ""


def resolve_actor_context(config: RunnableConfig | None = None) -> tuple:
    configurable = (config or {}).get("configurable", {})
    return (
        configurable.get("actor_user_id"),
        configurable.get("actor_level"),
        configurable.get("tenant_id"),
        configurable.get("obra_id_ativa"),
    )


def _is_gateway_enabled() -> bool:
    raw = os.environ.get("AGENT_USE_GATEWAY", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def get_business_tools(
    actor_user_id: int,
    actor_level: str,
    *,
    tenant_id: int | None,
    obra_id_ativa: int | None,
):
    if _is_gateway_enabled():
        try:
            return get_gateway_tools(
                actor_user_id=actor_user_id,
                actor_level=actor_level,
                tenant_id=tenant_id,
                obra_id_ativa=obra_id_ativa,
            )
        except TypeError:
            return get_gateway_tools(actor_user_id=actor_user_id, actor_level=actor_level)
        except NameError:
            from ..tools import get_gateway_tools as _lazy
            try:
                return _lazy(actor_user_id=actor_user_id, actor_level=actor_level,
                             tenant_id=tenant_id, obra_id_ativa=obra_id_ativa)
            except TypeError:
                return _lazy(actor_user_id=actor_user_id, actor_level=actor_level)

    try:
        return get_database_tools(
            actor_user_id=actor_user_id, actor_level=actor_level,
            tenant_id=tenant_id,
        )
    except TypeError:
        return get_database_tools(actor_user_id=actor_user_id, actor_level=actor_level)
    except NameError:
        from ..tools import get_database_tools as _lazy  # type: ignore
        try:
            return _lazy(actor_user_id=actor_user_id, actor_level=actor_level,
                         tenant_id=tenant_id)
        except TypeError:
            return _lazy(actor_user_id=actor_user_id, actor_level=actor_level)


def resolve_tool_map(config: RunnableConfig | None = None) -> dict:
    actor_user_id, actor_level, tenant_id, obra_id_ativa = resolve_actor_context(config)
    if actor_user_id is None or actor_level is None:
        return {}

    configurable = (config or {}).get("configurable", {})
    telegram_chat_id = configurable.get("telegram_chat_id")
    thread_id = configurable.get("thread_id")
    telegram_message_thread_id = configurable.get("telegram_message_thread_id")
    conversa_id = configurable.get("conversa_id")

    tools = get_business_tools(
        actor_user_id=int(actor_user_id),
        actor_level=str(actor_level),
        tenant_id=int(tenant_id) if tenant_id is not None else None,
        obra_id_ativa=int(obra_id_ativa) if obra_id_ativa is not None else None,
    )
    tools.extend(
        get_telegram_tools(
            chat_id=str(telegram_chat_id) if telegram_chat_id is not None else None,
            thread_id=str(thread_id) if thread_id is not None else None,
            telegram_message_thread_id=int(telegram_message_thread_id) if telegram_message_thread_id is not None else None,
            actor_user_id=int(actor_user_id),
            actor_level=str(actor_level),
            conversa_id=int(conversa_id) if conversa_id is not None else None,
        )
    )
    return {tool.name: tool for tool in tools}


def ensure_required_fields(tool_name: str, tool_args: dict, config: RunnableConfig | None = None) -> str | None:
    if tool_name == "criar_registro":
        status = normalize_text(str(tool_args.get("status") or ""))
        if status != "aprovado":
            return None

        required = ["data", "tempo_manha", "tempo_tarde"]
        missing = [f for f in required if tool_args.get(f) in (None, "")]

        if not tool_args.get("frente_servico_id") and not tool_args.get("frente_servico_nome"):
            missing.append("frente_servico_nome")

        if not missing:
            return None
        return "Dados obrigatórios faltando para criar registro: " + ", ".join(missing) + ". Colete os campos faltantes antes de salvar."

    if tool_name == "criar_alerta":
        required = ["type"]
        missing = [f for f in required if tool_args.get(f) in (None, "")]
        if not missing:
            return None
        return "Dados obrigatórios faltando para criar alerta: " + ", ".join(missing) + ". Colete os campos faltantes antes de salvar."

    return None


def normalize_tool_output(tool_name: str, tool_output, config: RunnableConfig | None = None):
    if tool_name == "listar_registros" and isinstance(tool_output, list):
        if not tool_output:
            return {
                "ok": True, "total": 0, "items": [],
                "message": "Nenhum registro encontrado para os filtros informados.",
                "next_steps": ["consultar outra data", "consultar outra frente de servico",
                               "buscar por usuario/equipe", "revisar nome da frente"],
            }
        return {"ok": True, "total": len(tool_output), "items": tool_output}

    if tool_name == "listar_frentes_servico" and isinstance(tool_output, list):
        normalized_names = [normalize_text(str(item.get("nome", ""))) for item in tool_output if isinstance(item, dict)]
        duplicates = sorted({n for n in normalized_names if normalized_names.count(n) > 1 and n})
        if duplicates:
            return {"ok": True, "total": len(tool_output), "items": tool_output,
                    "warning": "Possiveis nomes duplicados/similares de frente encontrados.",
                    "normalized_duplicates": duplicates}
        return {"ok": True, "total": len(tool_output), "items": tool_output}

    if tool_name == "listar_alertas" and isinstance(tool_output, dict):
        if tool_output.get("ok") and tool_output.get("total") == 0:
            payload = dict(tool_output)
            payload.setdefault("next_steps", [
                "consultar outro status", "consultar outra severidade",
                "listar alertas por periodo no diario", "listar alertas recentes sem filtros",
            ])
            return payload
        return tool_output

    if tool_name in {"criar_registro", "atualizar_registro", "registrar_producao_diaria",
                     "atualizar_status_registro_operacional"} and isinstance(tool_output, dict):
        registro = tool_output.get("registro")
        if tool_name == "criar_registro" and not isinstance(registro, dict):
            registro = tool_output
        if isinstance(registro, dict):
            status = normalize_text(str(registro.get("status") or ""))
            if status != "aprovado":
                business_rag = BusinessRAGService()
                configurable = (config or {}).get("configurable", {})
                sugestao = business_rag.sugerir_campos_faltantes(
                    tipo_registro="producao_diaria",
                    dados_parciais=registro,
                    tenant_id=configurable.get("tenant_id"),
                    obra_id_ativa=configurable.get("obra_id_ativa"),
                )
                payload = dict(tool_output)
                if sugestao.get("ok"):
                    payload["faltantes"] = sugestao.get("faltantes", [])
                    payload["validacoes"] = sugestao.get("validacoes", [])
                    payload["completo_para_consolidar"] = bool(sugestao.get("pronto_para_consolidar"))
                    if payload["faltantes"] or payload["validacoes"]:
                        payload["next_steps"] = [
                            "coletar campos faltantes para consolidacao",
                            "atualizar o mesmo registro com as novas informacoes",
                            "consolidar somente quando estiver completo",
                        ]
                return payload

    return tool_output


def debit_credits(config: RunnableConfig | None = None) -> None:
    configurable = (config or {}).get("configurable", {})
    tenant_id = configurable.get("tenant_id")
    conversa_id = configurable.get("conversa_id")
    if tenant_id is None:
        return
    try:
        from backend.db.session import SessionLocal
        from backend.services.credito_service import debitar_creditos
        with SessionLocal() as db:
            debitar_creditos(db, int(tenant_id), "mensagem_agente",
                             referencia_id=str(conversa_id) if conversa_id else None)
    except Exception as exc:
        logger.warning("Falha ao debitar créditos: %s", exc)
