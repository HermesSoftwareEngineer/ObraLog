"""Responder node: synthesizes tool results into a final user-facing response."""
import logging

from langchain_core.runnables import RunnableConfig

try:
    from ..llms import llm_main
    from ..state import State
    from ..nodes._tool_utils import debit_credits
    from ..nodes.response import _build_system_message
except ImportError:
    from llms import llm_main  # type: ignore
    from state import State  # type: ignore
    from nodes._tool_utils import debit_credits  # type: ignore
    from nodes.response import _build_system_message  # type: ignore

logger = logging.getLogger("obralog.agent.responder")


def responder_node(state: State, config: RunnableConfig | None = None) -> dict:
    messages = list(state["messages"])
    system = _build_system_message(messages, config)

    # llm_main without tools — only synthesizes, does not call new tools
    response = llm_main.invoke([system] + messages)

    debit_credits(config)
    return {"messages": [response]}
