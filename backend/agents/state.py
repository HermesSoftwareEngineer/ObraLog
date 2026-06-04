from typing import Annotated

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    system_message: SystemMessage | None
    _system_msg_human_count: int | None
