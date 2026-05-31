"""Executor node: runs all tool calls from the plan in batch."""
import logging

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

try:
    from ..state import State
    from ..nodes._tool_utils import resolve_tool_map, ensure_required_fields, normalize_tool_output, normalize_text, last_human_text
except ImportError:
    from state import State  # type: ignore
    from nodes._tool_utils import resolve_tool_map, ensure_required_fields, normalize_tool_output, normalize_text, last_human_text  # type: ignore

logger = logging.getLogger("obralog.agent.executor")


def executor_node(state: State, config: RunnableConfig | None = None) -> dict:
    plan = state.get("plan") or {}
    tool_call_specs = plan.get("tool_calls", []) if isinstance(plan, dict) else []

    if not tool_call_specs:
        return {}

    tool_map = resolve_tool_map(config)

    # Build synthetic AIMessage so ToolMessages have valid tool_call_ids
    synthetic_tool_calls = [
        {
            "name": spec.get("name", ""),
            "args": spec.get("args", {}),
            "id": f"plan_{i}",
            "type": "tool_call",
        }
        for i, spec in enumerate(tool_call_specs)
    ]
    synthetic_ai = AIMessage(content="", tool_calls=synthetic_tool_calls)

    tool_messages = []
    messages = list(state.get("messages", []))

    for i, spec in enumerate(tool_call_specs):
        name = spec.get("name", "")
        args = spec.get("args", {})
        call_id = f"plan_{i}"

        tool_instance = tool_map.get(name)
        if not tool_instance:
            result = {"ok": False, "message": f"Tool desconhecida: {name}"}
        else:
            required_error = ensure_required_fields(name, args, config)
            if required_error:
                result = {"ok": False, "message": required_error}
            else:
                try:
                    result = tool_instance.invoke(args)
                    result = normalize_tool_output(name, result, config)
                except PermissionError:
                    last_human = normalize_text(last_human_text(messages))
                    if "engenheiro" in last_human and name in {
                        "criar_frente_servico", "atualizar_frente_servico", "deletar_frente_servico",
                    }:
                        result = {
                            "ok": False,
                            "message": (
                                "Permissão insuficiente no perfil atual para alterar frentes. "
                                "Ofereça abrir solicitação/encaminhamento para administrador ou gerente."
                            ),
                        }
                    else:
                        result = {"ok": False, "message": "Acesso negado para esta operação no perfil atual."}
                except Exception as exc:
                    logger.error("Erro ao executar tool %s: %s", name, exc)
                    result = {"ok": False, "message": str(exc)}

        tool_messages.append(ToolMessage(content=str(result), tool_call_id=call_id))

    return {"messages": [synthetic_ai] + tool_messages}
