from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    _system_prompt: str | None            # conteúdo serializado; reconstruído como SystemMessage no agent_node
    _system_prompt_human_count: int | None
