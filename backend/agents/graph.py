from langgraph.graph import StateGraph, START, END

try:
    from .state import State
    from .chat_db import checkpointer
    from .nodes.response import tools_step
    from .nodes.router import router_node, route_after_router
    from .nodes.planner import planner_node
    from .nodes.notifier import notifier_node
    from .nodes.executor import executor_node
    from .nodes.responder import responder_node
except ImportError:
    from state import State  # type: ignore
    from chat_db import checkpointer  # type: ignore
    from nodes.response import tools_step  # type: ignore
    from nodes.router import router_node, route_after_router  # type: ignore
    from nodes.planner import planner_node  # type: ignore
    from nodes.notifier import notifier_node  # type: ignore
    from nodes.executor import executor_node  # type: ignore
    from nodes.responder import responder_node  # type: ignore

graph_builder = StateGraph(State)

# --- Nós ---
graph_builder.add_node("router",    router_node)
graph_builder.add_node("tools",     tools_step)       # caminho simples: executa tools do router
graph_builder.add_node("planner",   planner_node)     # caminho complexo: cria plano
graph_builder.add_node("notifier",  notifier_node)    # envia "Estou verificando..." ao usuário
graph_builder.add_node("executor",  executor_node)    # executa tools do plano em batch
graph_builder.add_node("responder", responder_node)   # sintetiza resultado final

# --- Edges ---
graph_builder.add_edge(START, "router")

# Router decide: resposta direta (end), tools simples (tools) ou fluxo complexo (complex)
graph_builder.add_conditional_edges(
    "router",
    route_after_router,
    {
        "end":     END,
        "tools":   "tools",
        "complex": "planner",
    },
)

# Caminho simples: tools → router (loop até router responder direto)
graph_builder.add_edge("tools", "router")

# Caminho complexo: planner → notifier → executor → responder → END
graph_builder.add_edge("planner",   "notifier")
graph_builder.add_edge("notifier",  "executor")
graph_builder.add_edge("executor",  "responder")
graph_builder.add_edge("responder", END)

graph = graph_builder.compile(checkpointer=checkpointer)
