import logging
import time

from langgraph.graph import StateGraph, START, END

_logger = logging.getLogger("obralog.graph")

try:
    from .state import State
    from .chat_db import checkpointer
    from .nodes.response import tools_step
    from .nodes.agent import agent_node, route_after_agent
except ImportError:
    from state import State  # type: ignore
    from chat_db import checkpointer  # type: ignore
    from nodes.response import tools_step  # type: ignore
    from nodes.agent import agent_node, route_after_agent  # type: ignore

_logger.info("[GRAPH] compilando StateGraph")
_t = time.monotonic()

graph_builder = StateGraph(State)

graph_builder.add_node("agent", agent_node)
graph_builder.add_node("tools", tools_step)

graph_builder.add_edge(START, "agent")
graph_builder.add_conditional_edges(
    "agent",
    route_after_agent,
    {"tools": "tools", "end": END},
)
graph_builder.add_edge("tools", "agent")

graph = graph_builder.compile(checkpointer=checkpointer)
_logger.info("[GRAPH] StateGraph compilado em %.2fs checkpointer=%s", time.monotonic() - _t, type(checkpointer).__name__)
