from langgraph.graph import StateGraph, START, END

try:
	from .state import State
	from .nodes.response import responder
	from .chat_db import checkpointer
except ImportError:
	from state import State
	from nodes.response import responder
	from chat_db import checkpointer

graph_builder = StateGraph(State)

# Nodes
graph_builder.add_node("responder", responder)

# Edges
graph_builder.add_edge(START, "responder")
graph_builder.add_edge("responder", END)

# Build
graph = graph_builder.compile(checkpointer=checkpointer)