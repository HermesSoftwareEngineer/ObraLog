from __future__ import annotations

import difflib
import unicodedata
from typing import Literal

from langchain_core.tools import tool

from backend.db.models import AlertTypeAlias
from backend.db.session import SessionLocal

from backend.agents.context.vector_context import get_context_for_query
from backend.agents.gateway import (
    ActorContext,
    GatewayActionRouter,
    GatewayError,
    GatewayRequest,
    GatewayRequestMeta,
    GatewayService,
    GatewayValidationError,
)
from backend.agents.gateway.mappers import (
    map_alerta_to_business,
    map_consultar_alertas_operacionais_output,
    map_consultar_diario_obra_output,
    map_consultar_producao_periodo_output,
    parse_iso_date,
    strip_technical_keys,
)
from backend.agents.gateway.rag_service import BusinessRAGService
from backend.agents.gateway.location_profile import build_location_profile

from .database_tools import get_database_tools


ALLOWED_EXECUTION_INTENTS = {
    "registrar_producao",
    "registrar_alerta",
    "atualizar_registro",
    "consolidar_registro",
    "gerenciar_frente_servico",
    "gerenciar_tipo_alerta",
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
    "cadastrar_tipo_alerta": "gerenciar_tipo_alerta",
    "criar_tipo_alerta": "gerenciar_tipo_alerta",
    "atualizar_tipo_alerta": "gerenciar_tipo_alerta",
    "deletar_tipo_alerta": "gerenciar_tipo_alerta",
    "remover_tipo_alerta": "gerenciar_tipo_alerta",
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
    # Política atual: consolidação pronta deve seguir sem confirmação explícita.
    # Mantemos a função para compatibilidade de chamadas e testes.
    del status, intent
    return False


ExecutionIntentLiteral = Literal[
    "registrar_producao",
    "atualizar_registro",
    "consolidar_registro",
    "registrar_alerta",
    "gerenciar_frente_servico",
    "gerenciar_tipo_alerta",
]


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.strip().lower().split())


def _execute_gateway(action):
    try:
        return action().to_dict()
    except GatewayError as exc:
        return exc.to_dict()


def _normalize_alert_type_for_gateway(value: str | None) -> str:
    normalized = _normalize_text(value or "")
    canonical_values = [
        "maquina_quebrada",
        "acidente",
        "falta_material",
        "risco_seguranca",
        "outro",
    ]
    if not normalized:
        raise GatewayValidationError(
            "tipo_alerta é obrigatório para registrar o alerta.",
            details={
                "field": "tipo_alerta",
                "accepted": canonical_values,
            },
            next_steps=[
                "pedir ao usuario para informar o tipo do alerta",
                "se nenhum tipo existente servir, usar 'outro' e descrever a ocorrencia",
            ],
        )

    aliases = {
        "maquina quebrada": "maquina_quebrada",
        "maquina quebrado": "maquina_quebrada",
        "maquina quebrou": "maquina_quebrada",
        "maquina parada": "maquina_quebrada",
        "maquina com defeito": "maquina_quebrada",
        "maquina com falha": "maquina_quebrada",
        "maquina_quebrada": "maquina_quebrada",
        "equipamento quebrado": "maquina_quebrada",
        "equipamento quebrou": "maquina_quebrada",
        "equipamento com defeito": "maquina_quebrada",
        "equipamento com falha": "maquina_quebrada",
        "falha de equipamento": "maquina_quebrada",
        "quebra de maquina": "maquina_quebrada",
        "acidente": "acidente",
        "colisao": "acidente",
        "atropelamento": "acidente",
        "queda": "acidente",
        "incidente": "acidente",
        "falta material": "falta_material",
        "falta de material": "falta_material",
        "falta de insumo": "falta_material",
        "falta insumo": "falta_material",
        "material nao chegou": "falta_material",
        "material nao veio": "falta_material",
        "atraso de material": "falta_material",
        "atraso material": "falta_material",
        "falta_material": "falta_material",
        "risco seguranca": "risco_seguranca",
        "risco de seguranca": "risco_seguranca",
        "alerta de seguranca": "risco_seguranca",
        "risco": "risco_seguranca",
        "inseguranca": "risco_seguranca",
        "condicao insegura": "risco_seguranca",
        "risco_seguranca": "risco_seguranca",
        "outro": "outro",
        "ocorrencia": "outro",
        "ocorrencia operacional": "outro",
        "alerta operacional": "outro",
    }
    parsed = aliases.get(normalized)
    if parsed:
        return parsed

    try:
        with SessionLocal() as db:
            alias_entry = (
                db.query(AlertTypeAlias)
                .filter(AlertTypeAlias.normalized_alias == normalized)
                .filter(AlertTypeAlias.ativo.is_(True))
                .first()
            )
            if alias_entry and alias_entry.canonical_type:
                if hasattr(alias_entry.canonical_type, "value"):
                    return alias_entry.canonical_type.value
                return str(alias_entry.canonical_type)
    except Exception:
        # Falha de acesso ao banco não deve mascarar a validação do tipo.
        pass

    suggestions = difflib.get_close_matches(normalized, list(aliases.keys()), n=3, cutoff=0.45)
    suggested_types: list[str] = []
    for suggestion in suggestions:
        parsed = aliases.get(suggestion)
        if parsed and parsed not in suggested_types:
            suggested_types.append(parsed)

    raise GatewayValidationError(
        "tipo_alerta inválido. Use: maquina_quebrada, acidente, falta_material, risco_seguranca, outro.",
        details={
            "field": "tipo_alerta",
            "received": value,
            "accepted": canonical_values,
            "suggested_types": suggested_types,
        },
        next_steps=[
            "pedir ao usuario para escolher um dos tipos aceitos",
            "se o tipo desejado ainda nao existir, usar 'outro' e registrar a descricao do novo tipo desejado",
            "se o usuario quiser manter esse tipo para proximos usos, cadastrar alias com criar_tipo_alerta_operacional",
            "se fizer sentido, reapresentar as opcoes: maquina_quebrada, acidente, falta_material, risco_seguranca, outro",
        ],
    )


def _resolve_alert_identifier(codigo_alerta: str | None = None, alert_id: str | None = None) -> dict:
    if alert_id:
        return {"ok": True, "alert_id": str(alert_id), "alert_code": codigo_alerta}
    if not codigo_alerta:
        return {
            "ok": False,
            "message": "Informe codigo_alerta ou alert_id para identificar o alerta.",
            "next_steps": [
                "pedir ao usuario o codigo do alerta, por exemplo ALT-2026-0001",
                "consultar alertas operacionais para localizar o codigo correto",
            ],
        }
    return {"ok": True, "alert_code": str(codigo_alerta).strip(), "alert_id": alert_id}


def get_gateway_tools(
    actor_user_id: int,
    actor_level: str,
    *,
    tenant_id: int | None = None,
    obra_id_ativa: int | None = None,
    location_profile: str | None = None,
):
    gateway = GatewayService()
    router = GatewayActionRouter(gateway)
    resolved_location_mode = build_location_profile(location_profile).mode
    business_rag = BusinessRAGService()
    try:
        database_tools = get_database_tools(
            actor_user_id,
            actor_level,
            tenant_id=tenant_id,
            location_profile=resolved_location_mode,
        )
    except TypeError:
        database_tools = get_database_tools(actor_user_id, actor_level)

    internal_tools = {tool_instance.name: tool_instance for tool_instance in database_tools}

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

    def _list_obras() -> list[dict]:
        items = _invoke_internal("listar_obras", {})
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

    def _resolve_location_mode(
        *,
        localizacao: dict | None,
        estaca_inicial: float | None,
        estaca_final: float | None,
        km_inicial: float | None,
        km_final: float | None,
        local_descritivo: str | None,
    ) -> str:
        localizacao_input = localizacao or {}
        explicit_type = str(localizacao_input.get("tipo") or "").strip().lower()
        if explicit_type in {"estaca", "km", "texto", "text"}:
            return "texto" if explicit_type == "text" else explicit_type

        has_estaca_values = estaca_inicial is not None or estaca_final is not None
        has_km_values = km_inicial is not None or km_final is not None

        detail_value = localizacao_input.get("detalhe_texto", local_descritivo)
        has_detail = isinstance(detail_value, str) and bool(detail_value.strip())

        if has_km_values:
            return "km"
        if has_estaca_values:
            return "estaca"
        if has_detail:
            return "texto"
        return resolved_location_mode

    def _resolve_obra_selection(obra_id: int | None = None, obra: str | None = None) -> dict:
        if obra_id is not None:
            return {"ok": True, "obra_id": int(obra_id)}
        if not obra:
            return {"ok": True, "obra_id": None}

        items = _list_obras()
        if not items:
            return {
                "ok": False,
                "message": "Nao foi possivel resolver obra no momento.",
                "next_steps": ["tentar novamente em alguns segundos", "informar o nome exato da obra"],
            }

        target = _normalize_text(obra)
        exact = [item for item in items if _normalize_text(str(item.get("nome") or "")) == target]
        exact_code = [item for item in items if _normalize_text(str(item.get("codigo") or "")) == target]
        candidates = exact or exact_code
        if len(candidates) == 1:
            return {"ok": True, "obra_id": int(candidates[0]["id"])}

        partial = [item for item in items if target in _normalize_text(str(item.get("nome") or ""))]
        if len(partial) == 1:
            return {"ok": True, "obra_id": int(partial[0]["id"])}

        if len(candidates) > 1 or len(partial) > 1:
            source = candidates if len(candidates) > 1 else partial
            options = [str(item.get("nome") or "").strip() for item in source[:8] if str(item.get("nome") or "").strip()]
            return {
                "ok": False,
                "message": f"Nome de obra ambiguo. Opcoes: {', '.join(options)}",
                "opcoes": options,
                "next_steps": ["pedir ao usuario para escolher uma das opcoes", "usar nome ou codigo exato da obra"],
            }

        options = [str(item.get("nome") or "").strip() for item in items[:8] if str(item.get("nome") or "").strip()]
        return {
            "ok": False,
            "message": f"Obra nao encontrada para '{obra}'. Opcoes cadastradas: {', '.join(options)}.",
            "opcoes": options,
            "next_steps": ["pedir ao usuario para informar nome/codigo exato da obra", "cadastrar a obra, se permitido"],
        }

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
                    "Se essa frente ainda nao existe, voce pode cadastrar, caso o usuario deseje (se seu perfil tiver permissao)."
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
                "Se essa frente ainda nao existe, voce pode cadastrar, caso o usuario deseje (se seu perfil tiver permissao)."
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
        data_normalizada = parse_iso_date(data, "data").isoformat()
        request = _request(
            "consultar_diario_obra",
            payload={"data": data_normalizada, "frente_servico": frente_servico},
            action_route="consulta",
            business_tool="consultar_diario_obra",
            technical_operation="consultar_diario_dia",
        )

        def handler(_: GatewayRequest) -> dict:
            resolved = _resolve_frente_servico_selection(frente_servico)
            if not resolved.get("ok"):
                return resolved

            frente_id = resolved.get("frente_servico_id")
            result = _invoke_internal("consultar_diario_dia", {"data": data_normalizada, "frente_servico_id": frente_id})
            raw = result if isinstance(result, dict) else {"resultado": result}
            mapped = map_consultar_diario_obra_output(
                raw,
                frentes_by_id=_build_frentes_by_id(),
                requested_frente_nome=(frente_servico or None),
            )
            payload = strip_technical_keys(mapped)
            payload["perfil_localizacao"] = resolved_location_mode
            payload["tenant_id"] = tenant_id
            return payload

        return _execute_gateway(lambda: router.consulta(request, handler))

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

        return _execute_gateway(lambda: router.consulta(request, handler))

    @tool
    def listar_obras_operacional() -> dict:
        """Lista obras em linguagem de negócio para vinculação de registros e alertas."""
        request = _request(
            "listar_obras_operacional",
            payload={},
            action_route="consulta",
            business_tool="listar_obras_operacional",
            technical_operation="listar_obras",
        )

        def handler(_: GatewayRequest) -> dict:
            items = _invoke_internal("listar_obras", {})
            if not isinstance(items, list):
                return {"ok": True, "total": 0, "obras": []}
            normalized_items = [item for item in items if isinstance(item, dict)]
            return {
                "ok": True,
                "total": len(normalized_items),
                "obras": strip_technical_keys(normalized_items),
            }

        return _execute_gateway(lambda: router.consulta(request, handler))

    @tool
    def criar_obra_operacional(
        nome: str,
        codigo: str | None = None,
        descricao: str | None = None,
        ativo: bool = True,
        intencao: ExecutionIntentLiteral = "gerenciar_frente_servico",
    ) -> dict:
        """Cria obra operacional no tenant atual."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="gerenciar_frente_servico")
        request = _request(
            "criar_obra_operacional",
            payload={
                "nome": nome,
                "codigo": codigo,
                "descricao": descricao,
                "ativo": ativo,
                "intencao": intencao_resolvida,
            },
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="criar_obra_operacional",
            technical_operation="criar_obra",
        )

        def handler(_: GatewayRequest) -> dict:
            result = _invoke_internal(
                "criar_obra",
                {
                    "nome": nome,
                    "codigo": codigo,
                    "descricao": descricao,
                    "ativo": bool(ativo),
                },
            )
            if isinstance(result, dict):
                return {"ok": True, "obra": strip_technical_keys(result)}
            return {"ok": True, "resultado": result}

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

    @tool
    def atualizar_obra_operacional(
        obra_id: int,
        nome: str | None = None,
        codigo: str | None = None,
        descricao: str | None = None,
        ativo: bool | None = None,
        intencao: ExecutionIntentLiteral = "gerenciar_frente_servico",
    ) -> dict:
        """Atualiza obra operacional."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="gerenciar_frente_servico")
        request = _request(
            "atualizar_obra_operacional",
            payload={
                "obra_id": obra_id,
                "nome": nome,
                "codigo": codigo,
                "descricao": descricao,
                "ativo": ativo,
                "intencao": intencao_resolvida,
            },
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="atualizar_obra_operacional",
            technical_operation="atualizar_obra",
        )

        def handler(_: GatewayRequest) -> dict:
            result = _invoke_internal(
                "atualizar_obra",
                {
                    "obra_id": int(obra_id),
                    "nome": nome,
                    "codigo": codigo,
                    "descricao": descricao,
                    "ativo": ativo,
                },
            )
            if isinstance(result, dict):
                return strip_technical_keys(result)
            return {"ok": True, "resultado": result}

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

    @tool
    def deletar_obra_operacional(
        obra_id: int,
        intencao: ExecutionIntentLiteral = "gerenciar_frente_servico",
    ) -> dict:
        """Remove obra operacional."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="gerenciar_frente_servico")
        request = _request(
            "deletar_obra_operacional",
            payload={"obra_id": obra_id, "intencao": intencao_resolvida},
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="deletar_obra_operacional",
            technical_operation="deletar_obra",
        )

        def handler(_: GatewayRequest) -> dict:
            result = _invoke_internal("deletar_obra", {"obra_id": int(obra_id)})
            if isinstance(result, dict):
                return strip_technical_keys(result)
            return {"ok": bool(result)}

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

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

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

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

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

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

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

    @tool
    def consultar_producao_periodo(
        data_inicio: str,
        data_fim: str,
        frente_servico: str | None = None,
        apenas_impraticaveis: bool = False,
    ) -> dict:
        """Consulta producao e resumo por periodo, com opcao de filtro por frente e dias impraticaveis."""
        data_inicio_normalizada = parse_iso_date(data_inicio, "data_inicio").isoformat()
        data_fim_normalizada = parse_iso_date(data_fim, "data_fim").isoformat()
        request = _request(
            "consultar_producao_periodo",
            payload={
                "data_inicio": data_inicio_normalizada,
                "data_fim": data_fim_normalizada,
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
                    "data_inicio": data_inicio_normalizada,
                    "data_fim": data_fim_normalizada,
                    "frente_servico_id": frente_id,
                    "apenas_impraticaveis": bool(apenas_impraticaveis),
                },
            )
            raw = result if isinstance(result, dict) else {"resultado": result}
            mapped = map_consultar_producao_periodo_output(raw, frentes_by_id=_build_frentes_by_id())
            payload = strip_technical_keys(mapped)
            payload["perfil_localizacao"] = resolved_location_mode
            payload["tenant_id"] = tenant_id
            return payload

        return _execute_gateway(lambda: router.consulta(request, handler))

    @tool
    def consultar_alertas_operacionais(
        status: str | None = None,
        severidade: str | None = None,
        obra_id: int | None = None,
        obra: str | None = None,
        apenas_nao_lidos: bool = False,
        limite: int = 50,
    ) -> dict:
        """Consulta alertas operacionais por status e severidade em linguagem de negocio."""
        request = _request(
            "consultar_alertas_operacionais",
            payload={
                "status": status,
                "severidade": severidade,
                "obra_id": obra_id,
                "obra": obra,
                "apenas_nao_lidos": apenas_nao_lidos,
                "limite": limite,
            },
            action_route="consulta",
            business_tool="consultar_alertas_operacionais",
            technical_operation="listar_alertas",
        )

        def handler(_: GatewayRequest) -> dict:
            resolved_obra = _resolve_obra_selection(obra_id=obra_id, obra=obra)
            if not resolved_obra.get("ok"):
                return resolved_obra

            result = _invoke_internal(
                "listar_alertas",
                {
                    "status": status,
                    "severity": severidade,
                    "obra_id": resolved_obra.get("obra_id"),
                    "apenas_nao_lidos": bool(apenas_nao_lidos),
                    "limit": max(1, min(int(limite), 200)),
                },
            )
            raw = result if isinstance(result, dict) else {"resultado": result}
            mapped = map_consultar_alertas_operacionais_output(raw)
            return strip_technical_keys(mapped)

        return _execute_gateway(lambda: router.consulta(request, handler))

    @tool
    def consultar_alerta_operacional(codigo_alerta: str | None = None, alert_id: str | None = None) -> dict:
        """Consulta um alerta operacional especifico por codigo de negocio ou UUID."""
        request = _request(
            "consultar_alerta_operacional",
            payload={"codigo_alerta": codigo_alerta, "alert_id": alert_id},
            action_route="consulta",
            business_tool="consultar_alerta_operacional",
            technical_operation="obter_alerta",
        )

        def handler(_: GatewayRequest) -> dict:
            resolved = _resolve_alert_identifier(codigo_alerta=codigo_alerta, alert_id=alert_id)
            if not resolved.get("ok"):
                return resolved

            result = _invoke_internal(
                "obter_alerta",
                {
                    "alert_id": resolved.get("alert_id"),
                    "alert_code": resolved.get("alert_code"),
                },
            )
            if isinstance(result, dict):
                alerta_raw = result.get("alerta", result)
                return {"ok": True, "alerta": map_alerta_to_business(alerta_raw) if isinstance(alerta_raw, dict) else alerta_raw}
            return {"ok": True, "alerta": {"resultado": result}}

        return _execute_gateway(lambda: router.consulta(request, handler))

    @tool
    def listar_tipos_alerta_operacional(ativos_apenas: bool = False) -> dict:
        """Lista aliases de tipos de alerta e os tipos canônicos disponíveis."""
        request = _request(
            "listar_tipos_alerta_operacional",
            payload={"ativos_apenas": ativos_apenas},
            action_route="consulta",
            business_tool="listar_tipos_alerta_operacional",
            technical_operation="listar_tipos_alerta",
        )

        def handler(_: GatewayRequest) -> dict:
            result = _invoke_internal("listar_tipos_alerta", {"ativos_apenas": bool(ativos_apenas)})
            if isinstance(result, dict):
                return strip_technical_keys(result)
            return {"ok": True, "resultado": result}

        return _execute_gateway(lambda: router.consulta(request, handler))

    @tool
    def consultar_tipo_alerta_operacional(tipo_id: str | None = None, alias: str | None = None) -> dict:
        """Consulta um tipo de alerta cadastrado por UUID técnico ou alias de negócio."""
        request = _request(
            "consultar_tipo_alerta_operacional",
            payload={"tipo_id": tipo_id, "alias": alias},
            action_route="consulta",
            business_tool="consultar_tipo_alerta_operacional",
            technical_operation="obter_tipo_alerta",
        )

        def handler(_: GatewayRequest) -> dict:
            result = _invoke_internal("obter_tipo_alerta", {"tipo_id": tipo_id, "alias": alias})
            if isinstance(result, dict):
                return strip_technical_keys(result)
            return {"ok": True, "resultado": result}

        return _execute_gateway(lambda: router.consulta(request, handler))

    @tool
    def criar_tipo_alerta_operacional(
        alias: str,
        tipo_canonico: str,
        descricao: str | None = None,
        ativo: bool = True,
        confirmado: bool = False,
        intencao: ExecutionIntentLiteral = "gerenciar_tipo_alerta",
    ) -> dict:
        """Cria alias de tipo de alerta para mapear linguagem de negócio para tipo canônico."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="gerenciar_tipo_alerta")
        request = _request(
            "criar_tipo_alerta_operacional",
            payload={
                "alias": alias,
                "tipo_canonico": tipo_canonico,
                "descricao": descricao,
                "ativo": ativo,
                "confirmado": confirmado,
                "intencao": intencao_resolvida,
            },
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="criar_tipo_alerta_operacional",
            technical_operation="criar_tipo_alerta",
        )

        def handler(_: GatewayRequest) -> dict:
            result = _invoke_internal(
                "criar_tipo_alerta",
                {
                    "alias": alias,
                    "tipo_canonico": tipo_canonico,
                    "descricao": descricao,
                    "ativo": bool(ativo),
                },
            )
            if isinstance(result, dict):
                return strip_technical_keys(result)
            return {"ok": True, "resultado": result}

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

    @tool
    def atualizar_tipo_alerta_operacional(
        tipo_id: str | None = None,
        alias: str | None = None,
        novo_alias: str | None = None,
        tipo_canonico: str | None = None,
        descricao: str | None = None,
        ativo: bool | None = None,
        confirmado: bool = False,
        intencao: ExecutionIntentLiteral = "gerenciar_tipo_alerta",
    ) -> dict:
        """Atualiza alias, tipo canônico, descrição ou status de um tipo de alerta."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="gerenciar_tipo_alerta")
        request = _request(
            "atualizar_tipo_alerta_operacional",
            payload={
                "tipo_id": tipo_id,
                "alias": alias,
                "novo_alias": novo_alias,
                "tipo_canonico": tipo_canonico,
                "descricao": descricao,
                "ativo": ativo,
                "confirmado": confirmado,
                "intencao": intencao_resolvida,
            },
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="atualizar_tipo_alerta_operacional",
            technical_operation="atualizar_tipo_alerta",
        )

        def handler(_: GatewayRequest) -> dict:
            result = _invoke_internal(
                "atualizar_tipo_alerta",
                {
                    "tipo_id": tipo_id,
                    "alias": alias,
                    "novo_alias": novo_alias,
                    "tipo_canonico": tipo_canonico,
                    "descricao": descricao,
                    "ativo": ativo,
                },
            )
            if isinstance(result, dict):
                return strip_technical_keys(result)
            return {"ok": True, "resultado": result}

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

    @tool
    def deletar_tipo_alerta_operacional(
        tipo_id: str | None = None,
        alias: str | None = None,
        confirmado: bool = False,
        intencao: ExecutionIntentLiteral = "gerenciar_tipo_alerta",
    ) -> dict:
        """Remove alias de tipo de alerta cadastrado."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="gerenciar_tipo_alerta")
        request = _request(
            "deletar_tipo_alerta_operacional",
            payload={
                "tipo_id": tipo_id,
                "alias": alias,
                "confirmado": confirmado,
                "intencao": intencao_resolvida,
            },
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="deletar_tipo_alerta_operacional",
            technical_operation="deletar_tipo_alerta",
        )

        def handler(_: GatewayRequest) -> dict:
            result = _invoke_internal("deletar_tipo_alerta", {"tipo_id": tipo_id, "alias": alias})
            if isinstance(result, dict):
                return strip_technical_keys(result)
            return {"ok": bool(result)}

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))


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

        return _execute_gateway(lambda: router.consulta(request, handler))

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
            return business_rag.sugerir_campos_faltantes(
                tipo_registro=tipo_registro,
                dados_parciais=dados_parciais or {},
                tenant_id=tenant_id,
                obra_id_ativa=obra_id_ativa,
                location_profile=resolved_location_mode,
            )

        return _execute_gateway(lambda: router.consulta(request, handler))

    @tool
    def registrar_producao_diaria(
        data: str,
        frente_servico: str,
        obra_id: int | None = None,
        obra: str | None = None,
        estaca_inicial: float | None = None,
        estaca_final: float | None = None,
        km_inicial: float | None = None,
        km_final: float | None = None,
        local_descritivo: str | None = None,
        localizacao: dict | None = None,
        tempo_manha: str | None = None,
        tempo_tarde: str | None = None,
        observacao: str | None = None,
        lado_pista: str | None = None,
        confirmado: bool = False,
        intencao: ExecutionIntentLiteral = "registrar_producao",
    ) -> dict:
        """Executa registro de producao diaria sem exigir confirmacao explicita."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="registrar_producao")
        data_normalizada = parse_iso_date(data, "data").isoformat()

        request = _request(
            "registrar_producao_diaria",
            payload={
                "data": data_normalizada,
                "obra_id": obra_id,
                "obra": obra,
                "frente_servico": frente_servico,
                "estaca_inicial": estaca_inicial,
                "estaca_final": estaca_final,
                "km_inicial": km_inicial,
                "km_final": km_final,
                "local_descritivo": local_descritivo,
                "localizacao": localizacao,
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
            resolved_obra = _resolve_obra_selection(obra_id=obra_id, obra=obra)
            if not resolved_obra.get("ok"):
                return resolved_obra

            resolved = _resolve_frente_servico_selection(frente_servico)
            if not resolved.get("ok"):
                return resolved

            frente_id = resolved.get("frente_servico_id")
            localizacao_input = localizacao or {}
            mode = _resolve_location_mode(
                localizacao=localizacao,
                estaca_inicial=estaca_inicial,
                estaca_final=estaca_final,
                km_inicial=km_inicial,
                km_final=km_final,
                local_descritivo=local_descritivo,
            )
            start_value = localizacao_input.get("valor_inicial", estaca_inicial if estaca_inicial is not None else km_inicial)
            end_value = localizacao_input.get("valor_final", estaca_final if estaca_final is not None else km_final)
            detail_value = localizacao_input.get("detalhe_texto", local_descritivo)

            result = _invoke_internal(
                "criar_registro",
                {
                    "data": data_normalizada,
                    "obra_id": resolved_obra.get("obra_id"),
                    "frente_servico_id": frente_id,
                    # Compatibilidade legado: estaca_* continua como alias de armazenamento.
                    "estaca_inicial": start_value,
                    "estaca_final": end_value,
                    "km_inicial": km_inicial,
                    "km_final": km_final,
                    "local_descritivo": detail_value,
                    "localizacao": {
                        "tipo": mode,
                        "valor_inicial": start_value,
                        "valor_final": end_value,
                        "detalhe_texto": detail_value,
                    },
                    "tempo_manha": tempo_manha,
                    "tempo_tarde": tempo_tarde,
                    "observacao": observacao,
                    "lado_pista": lado_pista,
                },
            )
            if isinstance(result, dict):
                return {
                    "registro": result,
                    "perfil_localizacao": mode,
                    "tenant_id": tenant_id,
                }
            return {
                "registro": {"resultado": result},
                "perfil_localizacao": mode,
                "tenant_id": tenant_id,
            }

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

    @tool
    def registrar_alerta_operacional(
        tipo_alerta: str,
        obra_id: int | None = None,
        obra: str | None = None,
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
                "obra_id": obra_id,
                "obra": obra,
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
            alert_type = _normalize_alert_type_for_gateway(tipo_alerta)
            resolved_obra = _resolve_obra_selection(obra_id=obra_id, obra=obra)
            if not resolved_obra.get("ok"):
                return resolved_obra

            result = _invoke_internal(
                "criar_alerta",
                {
                    "type": alert_type,
                    "obra_id": resolved_obra.get("obra_id"),
                    "description": descricao,
                    "severity": severidade,
                    "location_detail": local,
                    "equipment_name": equipamento,
                },
            )
            if isinstance(result, dict):
                alerta_raw = result.get("alerta", result)
                return {"ok": True, "alerta": map_alerta_to_business(alerta_raw) if isinstance(alerta_raw, dict) else alerta_raw}
            return {"alerta": {"resultado": result}}

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

    @tool
    def atualizar_alerta_operacional(
        status: str | None = None,
        codigo_alerta: str | None = None,
        alert_id: str | None = None,
        obra_id: int | None = None,
        obra: str | None = None,
        observacoes_resolucao: str | None = None,
        tipo_alerta: str | None = None,
        severidade: str | None = None,
        titulo: str | None = None,
        descricao: str | None = None,
        local: str | None = None,
        equipamento: str | None = None,
        fotos: list[str] | None = None,
        prioridade: int | None = None,
        canais_notificados: list[str] | None = None,
        confirmado: bool = False,
        intencao: ExecutionIntentLiteral = "registrar_alerta",
    ) -> dict:
        """Atualiza status e demais campos de um alerta operacional por codigo de negocio ou UUID."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="registrar_alerta")
        request = _request(
            "atualizar_alerta_operacional",
            payload={
                "codigo_alerta": codigo_alerta,
                "alert_id": alert_id,
                "status": status,
                "obra_id": obra_id,
                "obra": obra,
                "observacoes_resolucao": observacoes_resolucao,
                "tipo_alerta": tipo_alerta,
                "severidade": severidade,
                "titulo": titulo,
                "descricao": descricao,
                "local": local,
                "equipamento": equipamento,
                "fotos": fotos,
                "prioridade": prioridade,
                "canais_notificados": canais_notificados,
                "confirmado": confirmado,
                "intencao": intencao_resolvida,
            },
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="atualizar_alerta_operacional",
            technical_operation="atualizar_status_alerta",
        )

        def handler(_: GatewayRequest) -> dict:
            resolved = _resolve_alert_identifier(codigo_alerta=codigo_alerta, alert_id=alert_id)
            if not resolved.get("ok"):
                return resolved

            normalized_type = _normalize_alert_type_for_gateway(tipo_alerta) if tipo_alerta else None
            resolved_obra = _resolve_obra_selection(obra_id=obra_id, obra=obra)
            if not resolved_obra.get("ok"):
                return resolved_obra

            result = _invoke_internal(
                "atualizar_status_alerta",
                {
                    "alert_id": resolved.get("alert_id"),
                    "alert_code": resolved.get("alert_code"),
                    "status": status,
                    "obra_id": resolved_obra.get("obra_id"),
                    "resolution_notes": observacoes_resolucao,
                    "type": normalized_type,
                    "severity": severidade,
                    "title": titulo,
                    "description": descricao,
                    "location_detail": local,
                    "equipment_name": equipamento,
                    "photo_urls": fotos,
                    "priority_score": prioridade,
                    "notified_channels": canais_notificados,
                },
            )
            if isinstance(result, dict):
                alerta_raw = result.get("alerta", result)
                return {"ok": True, "alerta": map_alerta_to_business(alerta_raw) if isinstance(alerta_raw, dict) else alerta_raw}
            return {"ok": True, "alerta": {"resultado": result}}

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

    @tool
    def marcar_alerta_como_lido_operacional(
        codigo_alerta: str | None = None,
        alert_id: str | None = None,
        intencao: ExecutionIntentLiteral = "registrar_alerta",
    ) -> dict:
        """Marca um alerta operacional como lido por codigo de negocio ou UUID."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="registrar_alerta")
        request = _request(
            "marcar_alerta_como_lido_operacional",
            payload={"codigo_alerta": codigo_alerta, "alert_id": alert_id, "intencao": intencao_resolvida},
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="marcar_alerta_como_lido_operacional",
            technical_operation="marcar_alerta_como_lido",
        )

        def handler(_: GatewayRequest) -> dict:
            resolved = _resolve_alert_identifier(codigo_alerta=codigo_alerta, alert_id=alert_id)
            if not resolved.get("ok"):
                return resolved

            result = _invoke_internal(
                "marcar_alerta_como_lido",
                {
                    "alert_id": resolved.get("alert_id"),
                    "alert_code": resolved.get("alert_code"),
                },
            )
            if isinstance(result, dict):
                return strip_technical_keys(result)
            return {"ok": True, "resultado": result}

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

    @tool
    def marcar_alerta_como_nao_lido_operacional(
        codigo_alerta: str | None = None,
        alert_id: str | None = None,
        intencao: ExecutionIntentLiteral = "registrar_alerta",
    ) -> dict:
        """Marca um alerta operacional como não lido por codigo de negocio ou UUID."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="registrar_alerta")
        request = _request(
            "marcar_alerta_como_nao_lido_operacional",
            payload={"codigo_alerta": codigo_alerta, "alert_id": alert_id, "intencao": intencao_resolvida},
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="marcar_alerta_como_nao_lido_operacional",
            technical_operation="marcar_alerta_como_nao_lido",
        )

        def handler(_: GatewayRequest) -> dict:
            resolved = _resolve_alert_identifier(codigo_alerta=codigo_alerta, alert_id=alert_id)
            if not resolved.get("ok"):
                return resolved

            result = _invoke_internal(
                "marcar_alerta_como_nao_lido",
                {
                    "alert_id": resolved.get("alert_id"),
                    "alert_code": resolved.get("alert_code"),
                },
            )
            if isinstance(result, dict):
                return strip_technical_keys(result)
            return {"ok": True, "resultado": result}

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

    @tool
    def deletar_alerta_operacional(
        codigo_alerta: str | None = None,
        alert_id: str | None = None,
        confirmado: bool = False,
        intencao: ExecutionIntentLiteral = "registrar_alerta",
    ) -> dict:
        """Remove um alerta operacional por codigo de negocio ou UUID."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="registrar_alerta")
        request = _request(
            "deletar_alerta_operacional",
            payload={
                "codigo_alerta": codigo_alerta,
                "alert_id": alert_id,
                "confirmado": confirmado,
                "intencao": intencao_resolvida,
            },
            action_route="execucao",
            intent=intencao_resolvida,
            business_tool="deletar_alerta_operacional",
            technical_operation="deletar_alerta",
        )

        def handler(_: GatewayRequest) -> dict:
            resolved = _resolve_alert_identifier(codigo_alerta=codigo_alerta, alert_id=alert_id)
            if not resolved.get("ok"):
                return resolved

            result = _invoke_internal(
                "deletar_alerta",
                {
                    "alert_id": resolved.get("alert_id"),
                    "alert_code": resolved.get("alert_code"),
                },
            )
            if isinstance(result, dict):
                return strip_technical_keys(result)
            return {"ok": bool(result)}

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

    @tool
    def atualizar_status_registro_operacional(
        registro_id: int,
        status: str,
        confirmado: bool = False,
        intencao: ExecutionIntentLiteral = "atualizar_registro",
    ) -> dict:
        """Atualiza status do registro sem exigir confirmação explícita no gateway."""
        intencao_resolvida = _normalize_execution_intent(intencao, default="atualizar_registro")
        requires_confirmation = _requires_confirmation_for_status_change(status, intent=intencao_resolvida)

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
            return _execute_gateway(lambda: router.execucao(request, handler, intent=intencao_resolvida, confirmed=bool(confirmado)))
        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

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

        return _execute_gateway(lambda: router.execucao_sem_confirmacao(request, handler, intent=intencao_resolvida))

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

        return _execute_gateway(lambda: router.consulta(request, handler))

    return [
        consultar_diario_obra,
        listar_frentes_servico_operacional,
        listar_obras_operacional,
        consultar_producao_periodo,
        consultar_alertas_operacionais,
        consultar_alerta_operacional,
        listar_tipos_alerta_operacional,
        consultar_tipo_alerta_operacional,
        consultar_padroes_operacionais,
        sugerir_campos_faltantes,
        criar_frente_servico_operacional,
        atualizar_frente_servico_operacional,
        deletar_frente_servico_operacional,
        criar_obra_operacional,
        atualizar_obra_operacional,
        deletar_obra_operacional,
        registrar_producao_diaria,
        registrar_alerta_operacional,
        atualizar_alerta_operacional,
        marcar_alerta_como_lido_operacional,
        marcar_alerta_como_nao_lido_operacional,
        deletar_alerta_operacional,
        criar_tipo_alerta_operacional,
        atualizar_tipo_alerta_operacional,
        deletar_tipo_alerta_operacional,
        atualizar_status_registro_operacional,
        anexar_imagem_registro_operacional,
        buscar_contexto_operacional,
    ]
