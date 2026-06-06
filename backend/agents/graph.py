print("[BOOT] graph.py: início", flush=True)
import logging
import time

print("[BOOT] graph.py: importando langgraph...", flush=True)
from langgraph.graph import StateGraph, START, END
print("[BOOT] graph.py: langgraph OK", flush=True)

_logger = logging.getLogger("obralog.graph")

print("[BOOT] graph.py: importando state...", flush=True)
try:
    from .state import State
    print("[BOOT] graph.py: state OK (relativo)", flush=True)
    print("[BOOT] graph.py: importando chat_db (cria pool + checkpointer.setup)...", flush=True)
    from .chat_db import checkpointer
    print("[BOOT] graph.py: chat_db OK", flush=True)
    print("[BOOT] graph.py: importando nodes.response...", flush=True)
    from .nodes.response import tools_step
    print("[BOOT] graph.py: nodes.response OK", flush=True)
    print("[BOOT] graph.py: importando nodes.agent...", flush=True)
    from .nodes.agent import agent_node, route_after_agent
    print("[BOOT] graph.py: nodes.agent OK", flush=True)
except ImportError:
    from state import State  # type: ignore
    from chat_db import checkpointer  # type: ignore
    from nodes.response import tools_step  # type: ignore
    from nodes.agent import agent_node, route_after_agent  # type: ignore
    print("[BOOT] graph.py: imports via fallback OK", flush=True)

print("[BOOT] graph.py: criando StateGraph...", flush=True)
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

print("[BOOT] graph.py: compilando graph (compile)...", flush=True)
graph = graph_builder.compile(checkpointer=checkpointer)
print("[BOOT] graph.py: graph compilado OK", flush=True)
_logger.info("[GRAPH] StateGraph compilado em %.2fs checkpointer=%s", time.monotonic() - _t, type(checkpointer).__name__)
