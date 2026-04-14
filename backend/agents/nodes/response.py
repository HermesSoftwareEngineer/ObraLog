try:
    from ..llms import llm_main
    from ..state import State
    from ..tools import get_database_tools, get_gateway_tools, get_telegram_tools
    from ..prompts import build_system_prompt
    from ..context.vector_context import get_context_for_query
except ImportError:
    from llms import llm_main
    from state import State
    from tools import get_database_tools, get_gateway_tools, get_telegram_tools
    from prompts import build_system_prompt
    from context.vector_context import get_context_for_query

import unicodedata
import os
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from ..gateway.rag_service import BusinessRAGService


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.lower().strip().split())


def _last_human_text(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        return item["text"]
    return ""


def _build_system_message(state_messages: list, config: RunnableConfig | None = None) -> SystemMessage:
    configurable = (config or {}).get("configurable", {})
    actor_user_id = configurable.get("actor_user_id")
    actor_level = configurable.get("actor_level")
    actor_name = configurable.get("actor_name")
    actor_chat_display_name = configurable.get("actor_chat_display_name")
    conversation_date = configurable.get("conversation_date")
    conversation_date_br = configurable.get("conversation_date_br")

    if not conversation_date:
        conversation_date = datetime.now().date().isoformat()
    if not conversation_date_br and isinstance(conversation_date, str) and len(conversation_date) == 10:
        yyyy, mm, dd = conversation_date.split("-")
        conversation_date_br = f"{dd}/{mm}/{yyyy}"

    user_query = _last_human_text(state_messages)
    retrieved_context = get_context_for_query(user_query)
    context_block = (
        f"\n\nContexto operacional relevante:\n{retrieved_context}" if retrieved_context else ""
    )
    role_block = ""
    if actor_user_id is not None and actor_level is not None:
        role_block = (
            f"\n\nContexto do usuário atual:\n"
            f"- ID: {actor_user_id}\n"
            f"- Nome cadastrado: {actor_name or 'não informado'}\n"
            f"- Nome exibido no chat: {actor_chat_display_name or 'não informado'}\n"
            f"- Nível de acesso: {actor_level}\n"
            f"- Data atual da conversa (ISO): {conversation_date}\n"
            f"- Data atual da conversa (BR): {conversation_date_br or 'não informado'}"
        )

    user_hint_block = ""
    normalized_query = _normalize_text(user_query)
    incident_signals = ["nao chegou", "atras", "quebrou", "nao veio", "faltou", "incidente", "problema"]
    if any(signal in normalized_query for signal in incident_signals):
        user_hint_block += (
            "\n\nSinal operacional detectado na última mensagem:\n"
            "- O usuário pode ter relatado incidente de campo (material/equipamento/equipe). "
            "Reconheça e trate esse tópico junto com o registro principal."
        )
    if "meu perfil e engenheiro" in normalized_query or "perfil de engenheiro" in normalized_query:
        user_hint_block += (
            "\n\nSinal de papel declarado pelo usuário:\n"
            "- O usuário declarou perfil de engenheiro; se houver restrição de permissão, "
            "oriente fluxo de solicitação/encaminhamento de criação de frente sem encerrar em bloqueio passivo."
        )

    return SystemMessage(content=build_system_prompt() + role_block + context_block + user_hint_block)


def _ensure_required_fields(tool_name: str, tool_args: dict) -> str | None:
    if tool_name == "criar_registro":
        status = _normalize_text(str(tool_args.get("status") or ""))
        if status != "consolidado":
            return None

        required = [
            "data",
            "estaca_inicial",
            "estaca_final",
            "tempo_manha",
            "tempo_tarde",
        ]
        missing = [field for field in required if tool_args.get(field) in (None, "")]
        if not tool_args.get("frente_servico_id") and not tool_args.get("frente_servico_nome"):
            missing.append("frente_servico_nome")

        if not missing:
            return None

        return (
            "Dados obrigatórios faltando para criar registro: "
            + ", ".join(missing)
            + ". Colete os campos faltantes antes de salvar."
        )

    if tool_name == "criar_alerta":
        required = ["type"]
        missing = [field for field in required if tool_args.get(field) in (None, "")]

        if not missing:
            return None

        return (
            "Dados obrigatórios faltando para criar alerta: "
            + ", ".join(missing)
            + ". Colete os campos faltantes antes de salvar."
        )

    return None


def _normalize_tool_output(tool_name: str, tool_output):
    if tool_name == "listar_registros" and isinstance(tool_output, list):
        if not tool_output:
            return {
                "ok": True,
                "total": 0,
                "items": [],
                "message": "Nenhum registro encontrado para os filtros informados.",
                "next_steps": [
                    "consultar outra data",
                    "consultar outra frente de servico",
                    "buscar por usuario/equipe",
                    "revisar nome da frente",
                ],
            }
        return {"ok": True, "total": len(tool_output), "items": tool_output}

    if tool_name == "listar_frentes_servico" and isinstance(tool_output, list):
        normalized_names = [_normalize_text(str(item.get("nome", ""))) for item in tool_output if isinstance(item, dict)]
        duplicates = sorted({name for name in normalized_names if normalized_names.count(name) > 1 and name})
        if duplicates:
            return {
                "ok": True,
                "total": len(tool_output),
                "items": tool_output,
                "warning": "Possiveis nomes duplicados/similares de frente encontrados.",
                "normalized_duplicates": duplicates,
            }
        return {"ok": True, "total": len(tool_output), "items": tool_output}

    if tool_name == "listar_alertas" and isinstance(tool_output, dict):
        if tool_output.get("ok") and tool_output.get("total") == 0:
            payload = dict(tool_output)
            payload.setdefault(
                "next_steps",
                [
                    "consultar outro status",
                    "consultar outra severidade",
                    "listar alertas por periodo no diario",
                    "listar alertas recentes sem filtros",
                ],
            )
            return payload
        return tool_output

    if tool_name in {
        "criar_registro",
        "atualizar_registro",
        "registrar_producao_diaria",
        "atualizar_status_registro_operacional",
    } and isinstance(tool_output, dict):
        registro = tool_output.get("registro")
        if tool_name == "criar_registro" and not isinstance(registro, dict):
            registro = tool_output
        if isinstance(registro, dict):
            status = _normalize_text(str(registro.get("status") or ""))
            if status != "consolidado":
                business_rag = BusinessRAGService()
                sugestao = business_rag.sugerir_campos_faltantes(tipo_registro="producao_diaria", dados_parciais=registro)
                payload = dict(tool_output)
                if sugestao.get("ok"):
                    payload["faltantes"] = sugestao.get("faltantes", [])
                    payload["validacoes"] = sugestao.get("validacoes", [])
                    payload["completo_para_consolidar"] = bool(sugestao.get("pronto_para_consolidar"))
                    if payload["faltantes"] or payload["validacoes"]:
                        payload["next_steps"] = [
                            "coletar campos faltantes para consolidacao",
                            "atualizar o mesmo registro com as novas informacoes",
                            "consolidar somente quando estiver completo",
                        ]
                return payload

    return tool_output


def _resolve_actor_context(config: RunnableConfig | None = None) -> tuple[int | None, str | None]:
    configurable = (config or {}).get("configurable", {})
    actor_user_id = configurable.get("actor_user_id")
    actor_level = configurable.get("actor_level")
    return actor_user_id, actor_level


def _is_gateway_enabled() -> bool:
    raw = os.environ.get("AGENT_USE_GATEWAY", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _get_business_tools(actor_user_id: int, actor_level: str):
    if _is_gateway_enabled():
        try:
            return get_gateway_tools(actor_user_id=actor_user_id, actor_level=actor_level)
        except NameError:
            from ..tools import get_gateway_tools as lazy_get_gateway_tools

            return lazy_get_gateway_tools(actor_user_id=actor_user_id, actor_level=actor_level)

    try:
        return get_database_tools(actor_user_id=actor_user_id, actor_level=actor_level)
    except NameError:
        from ..tools import get_database_tools as lazy_get_database_tools

        return lazy_get_database_tools(actor_user_id=actor_user_id, actor_level=actor_level)


def _resolve_tool_map(config: RunnableConfig | None = None):
    actor_user_id, actor_level = _resolve_actor_context(config)
    if actor_user_id is None or actor_level is None:
        return {}

    configurable = (config or {}).get("configurable", {})
    telegram_chat_id = configurable.get("telegram_chat_id")
    thread_id = configurable.get("thread_id")
    telegram_message_thread_id = configurable.get("telegram_message_thread_id")

    tools = _get_business_tools(actor_user_id=int(actor_user_id), actor_level=str(actor_level))
    tools.extend(
        get_telegram_tools(
            chat_id=str(telegram_chat_id) if telegram_chat_id is not None else None,
            thread_id=str(thread_id) if thread_id is not None else None,
            telegram_message_thread_id=int(telegram_message_thread_id) if telegram_message_thread_id is not None else None,
            actor_user_id=int(actor_user_id),
            actor_level=str(actor_level),
        )
    )
    return {tool.name: tool for tool in tools}


def agent_step(state: State, config: RunnableConfig | None = None):
    state_messages = list(state["messages"])
    system_message = _build_system_message(state_messages, config)
    actor_user_id, actor_level = _resolve_actor_context(config)

    if actor_user_id is None or actor_level is None:
        response = llm_main.invoke([system_message] + state_messages)
        return {"messages": [response]}

    configurable = (config or {}).get("configurable", {})
    telegram_chat_id = configurable.get("telegram_chat_id")
    thread_id = configurable.get("thread_id")
    telegram_message_thread_id = configurable.get("telegram_message_thread_id")
    tools = _get_business_tools(actor_user_id=int(actor_user_id), actor_level=str(actor_level))
    tools.extend(
        get_telegram_tools(
            chat_id=str(telegram_chat_id) if telegram_chat_id is not None else None,
            thread_id=str(thread_id) if thread_id is not None else None,
            telegram_message_thread_id=int(telegram_message_thread_id) if telegram_message_thread_id is not None else None,
            actor_user_id=int(actor_user_id),
            actor_level=str(actor_level),
        )
    )
    model = llm_main.bind_tools(tools)
    response = model.invoke([system_message] + state_messages)
    return {"messages": [response]}


def tools_step(state: State, config: RunnableConfig | None = None):
    messages = list(state["messages"])
    if not messages:
        return {"messages": []}

    last_message = messages[-1]
    if not isinstance(last_message, AIMessage) or not getattr(last_message, "tool_calls", None):
        return {"messages": []}

    tool_map = _resolve_tool_map(config)
    tool_messages = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})
        tool_instance = tool_map.get(tool_name)
        if not tool_instance:
            tool_output = {"ok": False, "message": f"Tool inexistente: {tool_name}"}
        else:
            required_error = _ensure_required_fields(tool_name, tool_args)
            if required_error:
                tool_output = {"ok": False, "message": required_error}
                tool_messages.append(
                    ToolMessage(
                        content=str(tool_output),
                        tool_call_id=tool_call["id"],
                    )
                )
                continue

            try:
                tool_output = tool_instance.invoke(tool_args)
                tool_output = _normalize_tool_output(tool_name, tool_output)
            except PermissionError:
                last_human = _normalize_text(_last_human_text(messages))
                if "engenheiro" in last_human and tool_name in {
                    "criar_frente_servico",
                    "atualizar_frente_servico",
                    "deletar_frente_servico",
                }:
                    tool_output = {
                        "ok": False,
                        "message": (
                            "Permissão insuficiente no perfil atual para alterar frentes. "
                            "Ofereça abrir solicitação/encaminhamento para administrador ou gerente."
                        ),
                    }
                else:
                    tool_output = {"ok": False, "message": "Acesso negado para esta operação no perfil atual."}
            except Exception as exc:
                tool_output = {"ok": False, "message": str(exc)}

        tool_messages.append(
            ToolMessage(
                content=str(tool_output),
                tool_call_id=tool_call["id"],
            )
        )

    return {"messages": tool_messages}


def should_continue_to_tools(state: State) -> str:
    messages = list(state["messages"])
    if not messages:
        return "end"

    last_message = messages[-1]
    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "tools"
    return "end"


def responder(state: State, config: RunnableConfig | None = None):
    return agent_step(state, config)