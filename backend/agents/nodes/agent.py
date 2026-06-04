"""Agent node: unified ReAct agent."""
import logging
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

try:
    from ..llms import llm_main
    from ..state import State
    from ..nodes._tool_utils import resolve_tool_map, debit_credits
    from ..nodes.response import _build_system_message
except ImportError:
    from llms import llm_main  # type: ignore
    from state import State  # type: ignore
    from nodes._tool_utils import resolve_tool_map, debit_credits  # type: ignore
    from nodes.response import _build_system_message  # type: ignore

logger = logging.getLogger("obralog.agent.agent")


def agent_node(state: State, config: RunnableConfig | None = None) -> dict:
    _t0 = time.monotonic()
    chat_id = (config or {}).get("configurable", {}).get("telegram_chat_id", "?")
    messages = list(state["messages"])
    human_count = sum(1 for m in messages if isinstance(m, HumanMessage))
    logger.info("[GRAPH] agent_node iniciado - chat_id=%s msgs=%d", chat_id, len(messages))

    cached_prompt = state.get("_system_prompt")
    cached_count = state.get("_system_prompt_human_count")

    _t = time.monotonic()
    if cached_prompt is None or cached_count != human_count:
        system = _build_system_message(messages, config)
        updates = {"_system_prompt": system.content, "_system_prompt_human_count": human_count}
        cache_hit = False
    else:
        system = SystemMessage(content=cached_prompt)
        updates = {}
        cache_hit = True
    logger.info("[GRAPH] agent_node: system_message=%.2fs cache=%s chat_id=%s",
                time.monotonic() - _t, cache_hit, chat_id)

    _t = time.monotonic()
    tool_map = resolve_tool_map(config)
    logger.info("[GRAPH] agent_node: resolve_tool_map=%.2fs tools=%d chat_id=%s",
                time.monotonic() - _t, len(tool_map), chat_id)

    _t = time.monotonic()
    model = llm_main.bind_tools(list(tool_map.values()))
    logger.info("[GRAPH] agent_node: bind_tools=%.2fs chat_id=%s", time.monotonic() - _t, chat_id)

    _t = time.monotonic()
    response = model.invoke([system] + messages)
    tool_calls = [tc.get("name") for tc in (getattr(response, "tool_calls", None) or [])]
    logger.info("[GRAPH] agent_node: llm_invoke=%.2fs tool_calls=%s chat_id=%s",
                time.monotonic() - _t, tool_calls, chat_id)

    _t = time.monotonic()
    debit_credits(config)
    logger.info("[GRAPH] agent_node: debit_credits=%.2fs chat_id=%s", time.monotonic() - _t, chat_id)

    logger.info("[GRAPH] agent_node total=%.2fs chat_id=%s", time.monotonic() - _t0, chat_id)
    return {"messages": [response], **updates}


def route_after_agent(state: State) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools"
    return "end"
