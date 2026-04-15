from __future__ import annotations

import difflib
import unicodedata
from typing import Literal

from langchain_core.tools import tool

from backend.agents.context.vector_context import get_context_for_query
from backend.agents.gateway import (
    ActorContext,
    GatewayActionRouter,
    GatewayRequest,
    GatewayRequestMeta,
    GatewayService,
)
from backend.agents.gateway.mappers import (
    map_consultar_alertas_operacionais_output,
    map_consultar_diario_obra_output,
    map_consultar_producao_periodo_output,
    strip_technical_keys,
)
from backend.agents.gateway.rag_service import BusinessRAGService

from .database_tools import get_database_tools


ALLOWED_EXECUTION_INTENTS = {
    "registrar_producao",
    "registrar_alerta",
    "atualizar_registro",
    "consolidar_registro",
    "gerenciar_frente_servico",
}

EXECUTION_INTENT_ALIASES = {
    "criar_parcial": "registrar_producao",
    "criar_registro_parcial": "registrar_producao",
    "criar_registro": "registrar_producao",
    "abrir_registro": "registrar_producao",
    "registrar_parcial": "registrar_producao",
    "atualizar_parcial": "atualizar_registro",
    "anexar_imagem": "atualizar_registro",
    "anexar_foto": "atualizar_registro",
    "vincular_imagem": "atualizar_registro",
    "criar_frente": "gerenciar_frente_servico",
    "cadastrar_frente": "gerenciar_frente_servico",
    "atualizar_frente": "gerenciar_frente_servico",
    "editar_frente": "gerenciar_frente_servico",
    "deletar_frente": "gerenciar_frente_servico",
    "remover_frente": "gerenciar_frente_servico",
    "consolidar": "consolidar_registro",
}


def _normalize_execution_intent(intent: str | None, *, default: str) -> str:
    if not intent or not str(intent).strip():
        return default

    normalized = str(intent).strip().lower()
    normalized = EXECUTION_INTENT_ALIASES.get(normalized, normalized)
    if normalized in ALLOWED_EXECUTION_INTENTS:
        return normalized
    return default


def _requires_confirmation_for_status_change(status: str | None, *, intent: str | None = None) -> bool:
    normalized_status = (status or "").strip().lower()
    if normalized_status == "consolidado":
        return True
    normalized_intent = _normalize_execution_intent(intent, default="atualizar_registro")
    return normalized_intent == "consolidar_registro"


ExecutionIntentLiteral = Literal[
    "registrar_producao",
    "atualizar_registro",
    "consolidar_registro",
    "registrar_alerta",
    "gerenciar_frente_servico",
]


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.strip().lower().split())


def get_gateway_tools(actor_user_id: int, actor_level: str):
    gateway = GatewayService()
    router = GatewayActionRouter(gateway)
    business_rag = BusinessRAGService()
    internal_tools = {tool_instance.name: tool_instance for tool_instance in get_database_tools(actor_user_id, actor_level)}

    def _request(
        operation: str,
        payload: dict | None = None,
        *,
        action_route: str,
        intent: str | None = None,
        business_tool: str | None = None,
        technical_operation: str | None = None,
    ) -> GatewayRequest:
        return GatewayRequest(
            actor=ActorContext(actor_user_id=actor_user_id, actor_level=actor_level),
            meta=GatewayRequestMeta(
                operation=operation,
                action_route=action_route,
                intent=intent,
                business_tool=business_tool or operation,
                technical_operation=technical_operation,
                source="agent_gateway_tool",
            ),
            payload=payload or {},
        )

    def _invoke_internal(tool_name: str, tool_args: dict):
        tool_instance = internal_tools.get(tool_name)
        if not tool_instance:
            raise ValueError(f"Internal tool not available: {tool_name}")
        return tool_instance.invoke(tool_args)

    def _list_frentes_servico() -> list[dict]:
        items = _invoke_internal("listar_frentes_servico", {})
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    def _build_frentes_by_id() -> dict[int, str]:
        mapping: dict[int, str] = {}
        for item in _list_frentes_servico():
            item_id = item.get("id")
            item_nome = item.get("nome")
            if isinstance(item_id, int) and isinstance(item_nome, str) and item_nome.strip():
                mapping[item_id] = item_nome.strip()
        return mapping

    def _confirmation_required_response(operation: str, intent: str) -> dict:
        return {
            "ok": False,
            "message": "Preciso de confirmacao explicita antes de executar essa gravacao.",
            "operation": operation,
            "intent": intent,
            "next_steps": [
                "confirmar explicitamente a gravacao na conversa",
                "enviar novamente a operacao com confirmado=true",
            ],
        }

    def _resolve_frente_servico_selection(frente_servico_nome: str | None) -> dict:
        if not frente_servico_nome:
            return {"ok": True, "frente_servico_id": None}

        items = _list_frentes_servico()
        if not items:
            return {
                "ok": False,
                "message": "Nao foi possivel resolver frente de servico no momento.",
                "next_steps": ["tentar novamente em alguns segundos", "informar o nome exato da frente"],
            }

        target = _normalize_text(frente_servico_nome)
        exact = [item for item in items if _normalize_text(str(item.get("nome") or "")) == target]
        if len(exact) == 1:
            return {"ok": True, "frente_servico_id": exact[0]["id"]}

        partial = [item for item in items if target in _normalize_text(str(item.get("nome") or ""))]
        candidates = exact or partial
        if len(candidates) == 1:
            return {"ok": True, "frente_servico_id": candidates[0]["id"]}

        if len(candidates) > 1:
            options = [str(item.get("nome") or "").strip() for item in candidates[:8] if str(item.get("nome") or "").strip()]
            return {
                "ok": False,
                "message": f"Nome de frente ambiguo. Opcoes: {', '.join(options)}",
                "opcoes": options,
                "next_steps": ["pedir ao usuario para escolher uma das opcoes", "usar o nome exato da frente de servico"],
            }

        normalized_names = [_normalize_text(str(item.get("nome") or "")) for item in items]
        closest = difflib.get_close_matches(target, normalized_names, n=3, cutoff=0.35)
        suggested_names: list[str] = []
        if closest:
            lookup = {_normalize_text(str(item.get("nome") or "")): str(item.get("nome") or "").strip() for item in items}
            for value in closest:
                mapped_name = lookup.get(value)
                if mapped_name and mapped_name not in suggested_names:
                    suggested_names.append(mapped_name)

        options = [str(item.get("nome") or "").strip() for item in items[:8] if str(item.get("nome") or "").strip()]
        if suggested_names:
            sugestoes = ", ".join(suggested_names)
            return {
                "ok": False,
                "message": (
                    f"Frente nao encontrada para '{frente_servico_nome}'. "
                    f"Sugestoes por similaridade: {sugestoes}. "
                    f"Opcoes cadastradas: {', '.join(options)}. "
                    "Se essa frente ainda nao existe, voce pode cadastrar a frente de servico (se seu perfil tiver permissao)."
                ),
                "sugestoes": suggested_names,
                "opcoes": options,
                "next_steps": ["pedir ao usuario para confirmar o nome da frente", "usar uma sugestao por similaridade", "cadastrar a frente de servico, se permitido"],
            }

        return {
            "ok": False,
            "message": (
                f"Frente nao encontrada para '{frente_servico_nome}'. "
                "Use o nome da frente de servico (nao o local/trecho). "
                f"Opcoes cadastradas: {', '.join(options)}. "
                "Se essa frente ainda nao existe, voce pode cadastrar a frente de servico (se seu perfil tiver permissao)."
            ),
            "opcoes": options,
            "next_steps": ["pedir ao usuario para informar o nome exato da frente", "cadastrar a frente de servico, se permitido"],
        }

    def _resolve_frente_servico_id(frente_servico_nome: str | None) -> int | None:
        resolved = _resolve_frente_servico_selection(frente_servico_nome)
        if not resolved.get("ok"):
            raise ValueError(str(resolved.get("message") or "Nao foi possivel resolver frente de servico no momento."))
        return resolved.get("frente_servico_id")


    @tool
    def consultar_diario_obra(data: str, frente_servico: str | None = None) -> dict:
        """Consulta diario de obra de um dia por linguagem de negocio (data e nome da frente)."""
        request = _request(
            "consultar_diario_obra",
            payload={"data": data, "frente_servico": frente_servico},
            action_route="consulta",
            business_tool="consultar_diario_obra",
            technical_operation="consultar_diario_dia",
        )

        def handler(_: GatewayRequest) -> dict:
            resolved = _resolve_frente_servico_selection(frente_servico)
            if not resolved.get("ok"):
                return resolved

            frente_id = resolved.get("frente_servico_id")
            result = _invoke_internal("consultar_diario_dia", {"data": data, "frente_servico_id": frente_id})
            raw = result if isinstance(result, dict) else {"resultado": result}
            mapped = map_consultar_diario_obra_output(
                raw,
                frentes_by_id=_build_frentes_by_id(),
                requested_frente_nome=(frente_servico or None),
            )
            return strip_technical_keys(mapped)

        return router.consulta(request, handler).to_dict()

    @tool
    def listar_frentes_servico_operacional() -> dict:
        """Lista frentes de servico em linguagem de negocio para apoiar cadastro e filtros."""
        request = _request(
            "listar_frentes_servico_operacional",
            payload={},
            action_route="consulta",
            business_tool="listar_frentes_servico_operacional",
            technical_operation="listar_frentes_servico",
        )

        def handler(_: GatewayRequest) -> dict:
            items = _invoke_internal("listar_frentes_servico", {})
            if not isinstance(items, list):
                return {"ok": True, "total": 0, "frentes_servico": []}
            normalized_items = [item for item in items if isinstance(item, dict)]
            return {
                "ok": True,
                "total": len(normalized_items),
                "frentes_servico": strip_technical_keys(normalized_items),
            }

        return router.consulta(request, handler).to_dict()

    @tool
    def criar_frente_servico_operacional(
        nome: str,
        encarregado_responsavel: int | None = None,
        observacao: str | None = None,
        intencao: ExecutionIntentLiteral = "gerenciar_frente_servico",
    ) -> dict:
        """Cria frente de servico no gateway (administrador e gerente)."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="gerenciar_frente_servico")
        request = _request(
            "criar_frente_servico_operacional",
            payload={
                "nome": nome,
                "encarregado_responsavel": encarregado_responsavel,
                "observacao": observacao,
                "intencao": intencao_resolvida,
            },
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="criar_frente_servico_operacional",
            technical_operation="criar_frente_servico",
        )

        def handler(_: GatewayRequest) -> dict:
            result = _invoke_internal(
                "criar_frente_servico",
                {
                    "nome": nome,
                    "encarregado_responsavel": encarregado_responsavel,
                    "observacao": observacao,
                },
            )
            if isinstance(result, dict):
                frente = result.get("frente_servico", result)
                return {"ok": True, "frente_servico": strip_technical_keys(frente)}
            return {"ok": True, "resultado": result}

        return router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida).to_dict()

    @tool
    def atualizar_frente_servico_operacional(
        frente_id: int,
        nome: str | None = None,
        encarregado_responsavel: int | None = None,
        observacao: str | None = None,
        intencao: ExecutionIntentLiteral = "gerenciar_frente_servico",
    ) -> dict:
        """Atualiza frente de servico no gateway (administrador e gerente)."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="gerenciar_frente_servico")
        request = _request(
            "atualizar_frente_servico_operacional",
            payload={
                "frente_id": frente_id,
                "nome": nome,
                "encarregado_responsavel": encarregado_responsavel,
                "observacao": observacao,
                "intencao": intencao_resolvida,
            },
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="atualizar_frente_servico_operacional",
            technical_operation="atualizar_frente_servico",
        )

        def handler(_: GatewayRequest) -> dict:
            result = _invoke_internal(
                "atualizar_frente_servico",
                {
                    "frente_id": int(frente_id),
                    "nome": nome,
                    "encarregado_responsavel": encarregado_responsavel,
                    "observacao": observacao,
                },
            )
            if isinstance(result, dict):
                return strip_technical_keys(result)
            return {"ok": True, "resultado": result}

        return router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida).to_dict()

    @tool
    def deletar_frente_servico_operacional(
        frente_id: int,
        intencao: ExecutionIntentLiteral = "gerenciar_frente_servico",
    ) -> dict:
        """Remove frente de servico no gateway (administrador e gerente)."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="gerenciar_frente_servico")
        request = _request(
            "deletar_frente_servico_operacional",
            payload={
                "frente_id": frente_id,
                "intencao": intencao_resolvida,
            },
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="deletar_frente_servico_operacional",
            technical_operation="deletar_frente_servico",
        )

        def handler(_: GatewayRequest) -> dict:
            result = _invoke_internal(
                "deletar_frente_servico",
                {
                    "frente_id": int(frente_id),
                },
            )
            if isinstance(result, dict):
                return strip_technical_keys(result)
            return {"ok": bool(result)}

        return router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida).to_dict()

    @tool
    def consultar_producao_periodo(
        data_inicio: str,
        data_fim: str,
        frente_servico: str | None = None,
        apenas_impraticaveis: bool = False,
    ) -> dict:
        """Consulta producao e resumo por periodo, com opcao de filtro por frente e dias impraticaveis."""
        request = _request(
            "consultar_producao_periodo",
            payload={
                "data_inicio": data_inicio,
                "data_fim": data_fim,
                "frente_servico": frente_servico,
                "apenas_impraticaveis": apenas_impraticaveis,
            },
            action_route="consulta",
            business_tool="consultar_producao_periodo",
            technical_operation="consultar_diario_periodo",
        )

        def handler(_: GatewayRequest) -> dict:
            resolved = _resolve_frente_servico_selection(frente_servico)
            if not resolved.get("ok"):
                return resolved

            frente_id = resolved.get("frente_servico_id")
            result = _invoke_internal(
                "consultar_diario_periodo",
                {
                    "data_inicio": data_inicio,
                    "data_fim": data_fim,
                    "frente_servico_id": frente_id,
                    "apenas_impraticaveis": bool(apenas_impraticaveis),
                },
            )
            raw = result if isinstance(result, dict) else {"resultado": result}
            mapped = map_consultar_producao_periodo_output(raw, frentes_by_id=_build_frentes_by_id())
            return strip_technical_keys(mapped)

        return router.consulta(request, handler).to_dict()

    @tool
    def consultar_alertas_operacionais(
        status: str | None = None,
        severidade: str | None = None,
        apenas_nao_lidos: bool = False,
        limite: int = 50,
    ) -> dict:
        """Consulta alertas operacionais por status e severidade em linguagem de negocio."""
        request = _request(
            "consultar_alertas_operacionais",
            payload={
                "status": status,
                "severidade": severidade,
                "apenas_nao_lidos": apenas_nao_lidos,
                "limite": limite,
            },
            action_route="consulta",
            business_tool="consultar_alertas_operacionais",
            technical_operation="listar_alertas",
        )

        def handler(_: GatewayRequest) -> dict:
            result = _invoke_internal(
                "listar_alertas",
                {
                    "status": status,
                    "severity": severidade,
                    "apenas_nao_lidos": bool(apenas_nao_lidos),
                    "limit": max(1, min(int(limite), 200)),
                },
            )
            raw = result if isinstance(result, dict) else {"resultado": result}
            mapped = map_consultar_alertas_operacionais_output(raw)
            return strip_technical_keys(mapped)

        return router.consulta(request, handler).to_dict()


    @tool
    def consultar_padroes_operacionais(pergunta: str, k: int = 3) -> dict:
        """Consulta base de conhecimento operacional dedicada no estilo encarregado."""
        request = _request(
            "consultar_padroes_operacionais",
            payload={"pergunta": pergunta, "k": k},
            action_route="consulta",
            business_tool="consultar_padroes_operacionais",
            technical_operation="rag_business_knowledge",
        )

        def handler(_: GatewayRequest) -> dict:
            return business_rag.consultar_padroes_operacionais(pergunta=pergunta, k=k)

        return router.consulta(request, handler).to_dict()

    @tool
    def sugerir_campos_faltantes(tipo_registro: str, dados_parciais: dict) -> dict:
        """Sugere campos obrigatorios faltantes para completar registro operacional."""
        request = _request(
            "sugerir_campos_faltantes",
            payload={"tipo_registro": tipo_registro, "dados_parciais": dados_parciais},
            action_route="consulta",
            business_tool="sugerir_campos_faltantes",
            technical_operation="rag_business_checklist",
        )

        def handler(_: GatewayRequest) -> dict:
            return business_rag.sugerir_campos_faltantes(tipo_registro=tipo_registro, dados_parciais=dados_parciais or {})

        return router.consulta(request, handler).to_dict()

    @tool
    def registrar_producao_diaria(
        data: str,
        frente_servico: str,
        estaca_inicial: float,
        estaca_final: float,
        tempo_manha: str,
        tempo_tarde: str,
        observacao: str | None = None,
        lado_pista: str | None = None,
        confirmado: bool = False,
        intencao: ExecutionIntentLiteral = "registrar_producao",
    ) -> dict:
        """Executa registro de producao diaria sem exigir confirmacao explicita."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="registrar_producao")

        request = _request(
            "registrar_producao_diaria",
            payload={
                "data": data,
                "frente_servico": frente_servico,
                "estaca_inicial": estaca_inicial,
                "estaca_final": estaca_final,
                "tempo_manha": tempo_manha,
                "tempo_tarde": tempo_tarde,
                "observacao": observacao,
                "lado_pista": lado_pista,
                "confirmado": confirmado,
                "intencao": intencao_resolvida,
            },
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="registrar_producao_diaria",
            technical_operation="criar_registro",
        )

        def handler(_: GatewayRequest) -> dict:
            resolved = _resolve_frente_servico_selection(frente_servico)
            if not resolved.get("ok"):
                return resolved

            frente_id = resolved.get("frente_servico_id")
            result = _invoke_internal(
                "criar_registro",
                {
                    "data": data,
                    "frente_servico_id": frente_id,
                    "estaca_inicial": estaca_inicial,
                    "estaca_final": estaca_final,
                    "tempo_manha": tempo_manha,
                    "tempo_tarde": tempo_tarde,
                    "observacao": observacao,
                    "lado_pista": lado_pista,
                },
            )
            if isinstance(result, dict):
                return {"registro": result}
            return {"registro": {"resultado": result}}

        return router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida).to_dict()

    @tool
    def registrar_alerta_operacional(
        tipo_alerta: str,
        descricao: str | None = None,
        severidade: str | None = None,
        local: str | None = None,
        equipamento: str | None = None,
        confirmado: bool = False,
        intencao: ExecutionIntentLiteral = "registrar_alerta",
    ) -> dict:
        """Executa abertura de alerta operacional sem exigir confirmacao explicita."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="registrar_alerta")

        request = _request(
            "registrar_alerta_operacional",
            payload={
                "tipo_alerta": tipo_alerta,
                "descricao": descricao,
                "severidade": severidade,
                "local": local,
                "equipamento": equipamento,
                "confirmado": confirmado,
                "intencao": intencao_resolvida,
            },
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="registrar_alerta_operacional",
            technical_operation="criar_alerta",
        )

        def handler(_: GatewayRequest) -> dict:
            result = _invoke_internal(
                "criar_alerta",
                {
                    "type": tipo_alerta,
                    "description": descricao,
                    "severity": severidade,
                    "location_detail": local,
                    "equipment_name": equipamento,
                },
            )
            if isinstance(result, dict):
                return {"alerta": result.get("alerta", result)}
            return {"alerta": {"resultado": result}}

        return router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida).to_dict()

    @tool
    def atualizar_status_registro_operacional(
        registro_id: int,
        status: str,
        confirmado: bool = False,
        intencao: ExecutionIntentLiteral = "atualizar_registro",
    ) -> dict:
        """Atualiza status do registro; confirmacao explicita e exigida apenas para consolidacao."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="atualizar_registro")
        requires_confirmation = _requires_confirmation_for_status_change(status, intent=intencao_resolvida)
        if requires_confirmation and not bool(confirmado):
            return _confirmation_required_response("atualizar_status_registro_operacional", intencao_resolvida)

        request = _request(
            "atualizar_status_registro_operacional",
            payload={
                "registro_id": registro_id,
                "status": status,
                "confirmado": confirmado,
                "intencao": intencao_resolvida,
            },
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="atualizar_status_registro_operacional",
            technical_operation="atualizar_status_registro",
        )

        def handler(_: GatewayRequest) -> dict:
            result = _invoke_internal(
                "atualizar_status_registro",
                {
                    "registro_id": int(registro_id),
                    "status": status,
                },
            )
            if isinstance(result, dict):
                return strip_technical_keys({"registro": result.get("registro", result)})
            return strip_technical_keys({"registro": {"resultado": result}})

        if requires_confirmation:
            return router.execucao(request, handler, intent=intencao_resolvida, confirmed=True).to_dict()
        return router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida).to_dict()

    @tool
    def anexar_imagem_registro_operacional(
        registro_id: int,
        imagem_url: str,
        confirmado: bool = False,
        intencao: ExecutionIntentLiteral = "atualizar_registro",
    ) -> dict:
        """Anexa imagem (URL externa) a um registro operacional, incluindo registros consolidados, sem confirmacao explicita."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="atualizar_registro")

        request = _request(
            "anexar_imagem_registro_operacional",
            payload={
                "registro_id": registro_id,
                "imagem_url": imagem_url,
                "confirmado": confirmado,
                "intencao": intencao_resolvida,
            },
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="anexar_imagem_registro_operacional",
            technical_operation="anexar_imagem_registro",
        )

        def handler(_: GatewayRequest) -> dict:
            result = _invoke_internal(
                "anexar_imagem_registro",
                {
                    "registro_id": int(registro_id),
                    "imagem_url": imagem_url,
                },
            )
            if isinstance(result, dict):
                return strip_technical_keys(result)
            return {"ok": True, "resultado": result}

        return router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida).to_dict()

    @tool
    def buscar_contexto_operacional(pergunta: str, k: int = 3) -> dict:
        """RAG complementar: recupera contexto vetorial operacional da base indexada atual."""
        request = _request(
            "buscar_contexto_operacional",
            payload={"pergunta": pergunta, "k": k},
            action_route="consulta",
            business_tool="buscar_contexto_operacional",
            technical_operation="rag_vector_context",
        )

        def handler(_: GatewayRequest) -> dict:
            context = get_context_for_query(pergunta, k=max(1, min(int(k), 8)))
            return {
                "ok": True,
                "pergunta": pergunta,
                "contexto": context,
                "encontrado": bool(context.strip()),
            }

        return router.consulta(request, handler).to_dict()

    return [
        consultar_diario_obra,
        listar_frentes_servico_operacional,
        consultar_producao_periodo,
        consultar_alertas_operacionais,
        consultar_padroes_operacionais,
        sugerir_campos_faltantes,
        criar_frente_servico_operacional,
        atualizar_frente_servico_operacional,
        deletar_frente_servico_operacional,
        registrar_producao_diaria,
        registrar_alerta_operacional,
        atualizar_status_registro_operacional,
        anexar_imagem_registro_operacional,
        buscar_contexto_operacional,
    ]
