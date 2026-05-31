from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class ToolCallSpec(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    user_notification: str = Field(
        description="Mensagem curta para o usuário enquanto o plano é executado, ex: 'Verificando os dados, só um instante...'"
    )
    tool_calls: list[ToolCallSpec] = Field(
        description="Lista ordenada de ferramentas a chamar com seus argumentos"
    )


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    route: str | None        # "simple" | "complex" | None
    plan: dict | None        # ExecutionPlan.model_dump() quando route=="complex"
