"""Planner node: structured LLM that creates an ExecutionPlan from the conversation."""
import logging

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

try:
    from ..llms import llm_planner
    from ..state import ExecutionPlan, State
    from ..nodes._tool_utils import resolve_tool_map, last_human_text
    from ..nodes.response import _build_system_message
except ImportError:
    from llms import llm_planner  # type: ignore
    from state import ExecutionPlan, State  # type: ignore
    from nodes._tool_utils import resolve_tool_map, last_human_text  # type: ignore
    from nodes.response import _build_system_message  # type: ignore

logger = logging.getLogger("obralog.agent.planner")

_PLANNER_PROMPT = """
Você é um planejador de execução. Analise a conversa e crie um plano para atender a solicitação.

Ferramentas disponíveis:
{tools_description}

Retorne:
- user_notification: mensagem curta e direta para o usuário enquanto o plano roda.
  Exemplos: "Verificando os dados da frente, só um instante...", "Criando o registro, aguarde..."
  Seja específico sobre o que está fazendo. Sempre preencha este campo.
- tool_calls: lista ordenada das ferramentas a chamar, com os argumentos completos baseados
  nas informações já disponíveis na conversa. Inclua apenas chamadas cujos argumentos
  você consegue derivar da conversa. Se um passo depende do resultado de outro, inclua ambos
  na ordem correta — o executor os roda em sequência.
"""


def planner_node(state: State, config: RunnableConfig | None = None) -> dict:
    messages = list(state["messages"])

    tool_map = resolve_tool_map(config)
    tools_description = "\n".join(
        f"- {name}: {getattr(t, 'description', '')}" for name, t in tool_map.items()
    )

    planner_system = SystemMessage(
        content=_PLANNER_PROMPT.format(tools_description=tools_description)
    )

    structured_planner = llm_planner.with_structured_output(ExecutionPlan)
    try:
        plan: ExecutionPlan = structured_planner.invoke([planner_system] + messages)
        return {"plan": plan.model_dump(), "route": "complex"}
    except Exception as exc:
        logger.error("Falha ao gerar plano de execução: %s", exc)
        # Fallback: plano vazio com notificação genérica
        return {
            "plan": {"user_notification": "Processando sua solicitação...", "tool_calls": []},
            "route": "complex",
        }
