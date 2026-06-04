"""Simple agent node (router loop) and shared _build_system_message."""
try:
    from ..state import State
    from ..prompts import build_system_prompt
    from ..context.vector_context import get_context_for_query
    from ..nodes._tool_utils import resolve_tool_map, last_human_text, _execute_tool
except ImportError:
    from state import State  # type: ignore
    from prompts import build_system_prompt  # type: ignore
    from context.vector_context import get_context_for_query  # type: ignore
    from nodes._tool_utils import resolve_tool_map, last_human_text, _execute_tool  # type: ignore

from datetime import datetime
import logging
import time

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger("obralog.agent.response")


# ---------------------------------------------------------------------------
# System message builder — shared by agent_node
# ---------------------------------------------------------------------------

def _build_system_message(state_messages: list, config: RunnableConfig | None = None) -> SystemMessage:
    _t_total = time.monotonic()
    configurable = (config or {}).get("configurable", {})
    actor_user_id = configurable.get("actor_user_id")
    actor_level = configurable.get("actor_level")
    actor_name = configurable.get("actor_name")
    actor_chat_display_name = configurable.get("actor_chat_display_name")
    conversation_date = configurable.get("conversation_date")
    conversation_date_br = configurable.get("conversation_date_br")
    tenant_id = configurable.get("tenant_id")
    obra_id_ativa = configurable.get("obra_id_ativa")

    if not conversation_date:
        conversation_date = datetime.now().date().isoformat()
    if not conversation_date_br and isinstance(conversation_date, str) and len(conversation_date) == 10:
        yyyy, mm, dd = conversation_date.split("-")
        conversation_date_br = f"{dd}/{mm}/{yyyy}"

    user_query = last_human_text(state_messages)

    # Usa contexto pré-construído pelo telegram_processor (evita recalcular em cada node).
    # Fallback para cálculo inline se o cache não estiver disponível (ex: chat ou testes).
    prebuilt_vector_ctx = configurable.get("_prebuilt_vector_ctx")
    prebuilt_snapshot   = configurable.get("_prebuilt_snapshot")
    prebuilt_memories   = configurable.get("_prebuilt_memories")

    if prebuilt_vector_ctx is not None:
        retrieved_context = prebuilt_vector_ctx
    else:
        _t = time.monotonic()
        retrieved_context = get_context_for_query(user_query)
        _dt = time.monotonic() - _t
        if _dt > 1.0:
            logger.warning("[TIMING] get_context_for_query=%.2fs (fallback, sem cache)", _dt)

    context_block = (
        f"\n\nContexto operacional relevante:\n{retrieved_context}" if retrieved_context else ""
    )

    memory_block = ""
    tenant_snapshot_block = ""

    if prebuilt_snapshot is not None:
        tenant_snapshot_block = f"\n\n{prebuilt_snapshot}" if prebuilt_snapshot else ""
        memory_block = prebuilt_memories or ""
    elif tenant_id is not None:
        try:
            from backend.db.session import SessionLocal
            from backend.agents.context.tenant_snapshot import build_tenant_snapshot
            with SessionLocal() as _snap_db:
                _t = time.monotonic()
                snapshot = build_tenant_snapshot(
                    _snap_db, tenant_id, obra_id_ativa, actor_level
                )
                _dt = time.monotonic() - _t
                if _dt > 0.5:
                    logger.warning("[TIMING] build_tenant_snapshot=%.2fs (fallback, sem cache)", _dt)
                if snapshot:
                    tenant_snapshot_block = f"\n\n{snapshot}"
        except Exception:
            pass

    _total = time.monotonic() - _t_total
    if _total > 2.0:
        logger.warning("[TIMING] _build_system_message total=%.2fs", _total)

    role_block = ""
    if actor_user_id is not None and actor_level is not None:
        role_block = (
            f"\n\nContexto do usuário atual:\n"
            f"- ID: {actor_user_id}\n"
            f"- Nome cadastrado: {actor_name or 'não informado'}\n"
            f"- Nome exibido no chat: {actor_chat_display_name or 'não informado'}\n"
            f"- Nível de acesso: {actor_level}\n"
            f"- Data atual da conversa (ISO): {conversation_date}\n"
            f"- Data atual da conversa (BR): {conversation_date_br or 'não informado'}\n"
            f"- Tenant ativo: {tenant_id if tenant_id is not None else 'não informado'}\n"
            f"- Obra ativa: {obra_id_ativa if obra_id_ativa is not None else 'não informada'}"
        )

    return SystemMessage(content=build_system_prompt() + role_block + tenant_snapshot_block + context_block + memory_block)


# ---------------------------------------------------------------------------
# Tools step — executes tool calls from the last AIMessage
# ---------------------------------------------------------------------------

def tools_step(state: State, config: RunnableConfig | None = None):
    messages = list(state["messages"])
    if not messages:
        return {"messages": []}

    last_message = messages[-1]
    if not isinstance(last_message, AIMessage) or not getattr(last_message, "tool_calls", None):
        return {"messages": []}

    tool_map = resolve_tool_map(config)
    tool_messages = [
        ToolMessage(
            content=str(_execute_tool(tc.get("name"), tc.get("args", {}), messages, tool_map, config)),
            tool_call_id=tc["id"],
        )
        for tc in last_message.tool_calls
    ]
    return {"messages": tool_messages}
