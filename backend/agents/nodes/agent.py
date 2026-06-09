"""Agent node: unified ReAct agent."""
import logging
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.message import RemoveMessage

try:
    from ..llms import llm_main
    from ..state import State
    from ..nodes._tool_utils import resolve_tool_map, debit_credits
    from ..nodes.response import _build_system_message
    from ..compactacao import needs_compaction, compactar_conversa, compactar_conversa_async
except ImportError:
    from llms import llm_main  # type: ignore
    from state import State  # type: ignore
    from nodes._tool_utils import resolve_tool_map, debit_credits  # type: ignore
    from nodes.response import _build_system_message  # type: ignore
    from compactacao import needs_compaction, compactar_conversa, compactar_conversa_async  # type: ignore

logger = logging.getLogger("obralog.agent.agent")


def _maybe_compact(
    messages: list,
    config: RunnableConfig | None,
    chat_id: str,
) -> tuple[list, list]:
    """
    Se o contexto ultrapassar 50k tokens, compacta e retorna:
      (messages_para_llm, state_ops)

    messages_para_llm — lista reduzida enviada ao modelo neste turno.
    state_ops         — lista de RemoveMessage + novo SystemMessage de resumo
                        para aplicar ao state (via add_messages reducer).
    """
    if not needs_compaction(messages):
        return messages, []

    configurable = (config or {}).get("configurable", {})
    conversa_id = configurable.get("conversa_id")

    logger.info("[GRAPH] Compactação necessária chat_id=%s conversa_id=%s msgs=%d",
                chat_id, conversa_id, len(messages))

    if conversa_id is not None:
        try:
            from backend.db.session import SessionLocal
        except ImportError:
            from db.session import SessionLocal  # type: ignore
        try:
            with SessionLocal() as db:
                _t = time.monotonic()
                _, compressed = compactar_conversa(
                    db, conversa_id, messages, compress_state=True
                )
                logger.info("[GRAPH] Compactação sync=%.2fs chat_id=%s", time.monotonic() - _t, chat_id)
            if compressed:
                # compressed = [summary_SystemMessage, ...recent_messages...]
                # recent_messages são os mesmos objetos de `messages` (mesmo id())
                recent_ids = {id(m) for m in compressed[1:]}  # pula o novo SystemMessage
                to_remove = [
                    m for m in messages
                    if id(m) not in recent_ids and getattr(m, "id", None)
                ]
                remove_ops = [RemoveMessage(id=m.id) for m in to_remove]
                # compressed[0] é o novo SystemMessage de resumo — deve entrar no state
                summary_msg = compressed[0] if compressed else None
                state_ops = remove_ops + ([summary_msg] if summary_msg else [])
                return compressed, state_ops
        except Exception as exc:
            logger.error("[GRAPH] Falha na compactação síncrona: %s", exc)
    else:
        compactar_conversa_async(0, messages)

    # Fallback sem persitência: só janeia o que o LLM vê, sem alterar o state
    human_indices = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    if len(human_indices) > 6:
        cutoff = human_indices[-6]
        return messages[cutoff:], []

    return messages, []


def agent_node(state: State, config: RunnableConfig | None = None) -> dict:
    _t0 = time.monotonic()
    chat_id = (config or {}).get("configurable", {}).get("telegram_chat_id", "?")
    messages = list(state["messages"])
    logger.info("[GRAPH] agent_node iniciado - chat_id=%s msgs=%d", chat_id, len(messages))

    # --- Compactação mid-conversation (50k tokens) ---
    _t = time.monotonic()
    messages_for_llm, remove_ops = _maybe_compact(messages, config, chat_id)
    if remove_ops:
        logger.info("[GRAPH] agent_node: %d mensagens removidas do state chat_id=%s",
                    len(remove_ops), chat_id)
    logger.info("[GRAPH] agent_node: compaction_check=%.2fs chat_id=%s", time.monotonic() - _t, chat_id)

    human_count = sum(1 for m in messages_for_llm if isinstance(m, HumanMessage))

    cached_prompt = state.get("_system_prompt")
    cached_count = state.get("_system_prompt_human_count")

    _t = time.monotonic()
    if cached_prompt is None or cached_count != human_count:
        system = _build_system_message(messages_for_llm, config)
        sys_updates = {"_system_prompt": system.content, "_system_prompt_human_count": human_count}
        cache_hit = False
    else:
        system = SystemMessage(content=cached_prompt)
        sys_updates = {}
        cache_hit = True
    logger.info("[GRAPH] agent_node: system_message=%.2fs cache=%s chat_id=%s",
                time.monotonic() - _t, cache_hit, chat_id)

    pre_tool_map = (config or {}).get("configurable", {}).get("_pre_tool_map")
    if pre_tool_map is not None:
        tool_map = pre_tool_map
        logger.info("[GRAPH] agent_node: tool_map pre-built tools=%d chat_id=%s", len(tool_map), chat_id)
    else:
        logger.info("[GRAPH] agent_node: iniciando resolve_tool_map - chat_id=%s", chat_id)
        _t = time.monotonic()
        tool_map = resolve_tool_map(config)
        logger.info("[GRAPH] agent_node: resolve_tool_map=%.2fs tools=%d chat_id=%s",
                    time.monotonic() - _t, len(tool_map), chat_id)

    _t = time.monotonic()
    model = llm_main.bind_tools(list(tool_map.values()))
    logger.info("[GRAPH] agent_node: bind_tools=%.2fs chat_id=%s", time.monotonic() - _t, chat_id)

    _t = time.monotonic()
    response = model.invoke([system] + messages_for_llm)
    tool_calls = [tc.get("name") for tc in (getattr(response, "tool_calls", None) or [])]
    logger.info("[GRAPH] agent_node: llm_invoke=%.2fs tool_calls=%s chat_id=%s",
                time.monotonic() - _t, tool_calls, chat_id)

    _t = time.monotonic()
    debit_credits(config)
    logger.info("[GRAPH] agent_node: debit_credits=%.2fs chat_id=%s", time.monotonic() - _t, chat_id)

    logger.info("[GRAPH] agent_node total=%.2fs chat_id=%s", time.monotonic() - _t0, chat_id)

    # remove_ops vêm antes do response para que o reducer os processe na ordem certa
    all_msg_updates = remove_ops + [response]
    return {"messages": all_msg_updates, **sys_updates}


def route_after_agent(state: State) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools"
    return "end"
