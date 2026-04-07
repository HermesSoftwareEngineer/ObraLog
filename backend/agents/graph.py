from langgraph.graph import StateGraph, START, END

try:
	from .state import State
	from .nodes.response import agent_step, should_continue_to_tools, tools_step
	from .chat_db import checkpointer
except ImportError:
	from state import State
	from nodes.response import agent_step, should_continue_to_tools, tools_step
	from chat_db import checkpointer

graph_builder = StateGraph(State)

# Nodes
graph_builder.add_node("agent", agent_step)
graph_builder.add_node("tools", tools_step)

# Edges
graph_builder.add_edge(START, "agent")
graph_builder.add_conditional_edges(
	"agent",
	should_continue_to_tools,
	{
		"tools": "tools",
		"end": END,
	},
)
graph_builder.add_edge("tools", "agent")

# Build
graph = graph_builder.compile(checkpointer=checkpointer)