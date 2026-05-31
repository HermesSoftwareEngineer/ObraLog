"""Router node: fast LLM that handles simple requests directly or escalates to planner."""
import logging

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

try:
    from ..llms import llm_fast
    from ..state import State
    from ..nodes._tool_utils import resolve_tool_map, last_human_text, debit_credits
    from ..nodes.response import _build_system_message
except ImportError:
    from llms import llm_fast  # type: ignore
    from state import State  # type: ignore
    from nodes._tool_utils import resolve_tool_map, last_human_text, debit_credits  # type: ignore
    from nodes.response import _build_system_message  # type: ignore

logger = logging.getLogger("obralog.agent.router")

_ESCALATE_HINT = (
    "\n\nRegra de roteamento (não mostre ao usuário):\n"
    "- Se a solicitação exige 3 ou mais ações coordenadas e dependentes "
    "(ex: buscar schema + criar registro + validar campos + aprovar), "
    "chame `escalate_to_planner` com o motivo resumido.\n"
    "- Se puder responder diretamente ou com no máximo 2 ferramentas independentes, "
    "responda normalmente sem escalar.\n"
    "- Seja rápido e decisivo."
)


@tool
def escalate_to_planner(reason: str) -> str:
    """Escalar para o planejador quando a tarefa exige 3+ passos coordenados e dependentes."""
    return "escalated"


def router_node(state: State, config: RunnableConfig | None = None) -> dict:
    messages = list(state["messages"])
    base_system = _build_system_message(messages, config)
    system = SystemMessage(content=base_system.content + _ESCALATE_HINT)

    tool_map = resolve_tool_map(config)
    all_tools = list(tool_map.values()) + [escalate_to_planner]
    model = llm_fast.bind_tools(all_tools)

    response = model.invoke([system] + messages)

    tool_calls = getattr(response, "tool_calls", None) or []
    is_escalating = any(tc.get("name") == "escalate_to_planner" for tc in tool_calls)

    if is_escalating:
        # Não adiciona o AIMessage ao histórico — evita tool_call pendente sem ToolMessage
        return {"route": "complex"}

    debit_credits(config)
    return {"messages": [response], "route": "simple"}


def route_after_router(state: State) -> str:
    if state.get("route") == "complex":
        return "complex"

    messages = list(state["messages"])
    if not messages:
        return "end"

    last = messages[-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        # Ignora se o único tool_call for o escalate (não deveria chegar aqui, mas por segurança)
        non_escalate = [tc for tc in last.tool_calls if tc.get("name") != "escalate_to_planner"]
        if non_escalate:
            return "tools"

    return "end"
