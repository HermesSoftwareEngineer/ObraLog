"""Agent node: unified ReAct agent."""
import logging

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
    messages = list(state["messages"])
    human_count = sum(1 for m in messages if isinstance(m, HumanMessage))

    cached_prompt = state.get("_system_prompt")
    cached_count = state.get("_system_prompt_human_count")

    if cached_prompt is None or cached_count != human_count:
        system = _build_system_message(messages, config)
        updates = {"_system_prompt": system.content, "_system_prompt_human_count": human_count}
    else:
        system = SystemMessage(content=cached_prompt)
        updates = {}

    tool_map = resolve_tool_map(config)
    model = llm_main.bind_tools(list(tool_map.values()))
    response = model.invoke([system] + messages)
    debit_credits(config)

    return {"messages": [response], **updates}


def route_after_agent(state: State) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools"
    return "end"
