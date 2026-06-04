"""
Tools LangChain do agente — cada tool captura contexto via closure e delega
para o service correspondente em backend/services/.

Padrão:
    def handler() -> dict:
        return algum_service.funcao(tenant_id, actor_user_id, actor_level, ...)
    return _consulta("nome", handler)   # leitura
    return _execucao("nome", intent, handler)  # escrita
"""
from __future__ import annotations

import difflib
import logging
import time

from langchain_core.tools import tool

logger = logging.getLogger("obralog.agent.gateway_tools")

from backend.db.models import AlertTypeAlias
from backend.db.session import SessionLocal

from backend.agents.gateway import (
    GatewayError,
    GatewayValidationError,
    run_consulta,
    run_execucao,
)
from backend.agents.gateway.mappers import (
    map_alerta_to_business,
    map_consultar_alertas_operacionais_output,
    map_consultar_diario_obra_output,
    map_consultar_producao_periodo_output,
    map_registro_to_business,
    normalize_text,
    parse_iso_date,
    strip_technical_keys,
)
from backend.agents.gateway.policies import GatewayPolicyService
from backend.agents.gateway.rag_service import BusinessRAGService

import backend.services.alerta_service as _alerta_svc
import backend.services.alert_type_service as _alert_type_svc
import backend.services.frente_servico_service as _frente_svc
import backend.services.obra_service as _obra_svc
import backend.services.registro_service as _registro_svc


def _normalize_alert_type_for_gateway(value: str | None) -> str:
    normalized = normalize_text(value or "")
    canonical_values = ["maquina_quebrada", "acidente", "falta_material", "risco_seguranca", "outro"]

    if not normalized:
        raise GatewayValidationError(
            "tipo_alerta é obrigatório para registrar o alerta.",
            details={"field": "tipo_alerta", "accepted": canonical_values},
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
        pass

    suggestions = difflib.get_close_matches(normalized, list(aliases.keys()), n=3, cutoff=0.45)
    suggested_types: list[str] = []
    for suggestion in suggestions:
        canonical = aliases.get(suggestion)
        if canonical and canonical not in suggested_types:
            suggested_types.append(canonical)

    raise GatewayValidationError(
        "tipo_alerta inválido. Use: maquina_quebrada, acidente, falta_material, risco_seguranca, outro.",
        details={"field": "tipo_alerta", "received": value, "accepted": canonical_values, "suggested_types": suggested_types},
        next_steps=[
            "pedir ao usuario para escolher um dos tipos aceitos",
            "se o tipo desejado ainda nao existir, usar 'outro' e registrar a descricao do novo tipo desejado",
            "se o usuario quiser manter esse tipo para proximos usos, cadastrar alias com criar_tipo_alerta_operacional",
        ],
    )


def get_gateway_tools(
    actor_user_id: int,
    actor_level: str,
    *,
    tenant_id: int | None = None,
    obra_id_ativa: int | None = None,
):
    """Retorna as tools do agente com contexto de ator/tenant capturado em closure."""
    _t0 = time.monotonic()
    logger.info("[GATEWAY_TOOLS] get_gateway_tools: iniciando actor_user_id=%s actor_level=%s", actor_user_id, actor_level)

    _t = time.monotonic()
    business_rag = BusinessRAGService()
    logger.info("[GATEWAY_TOOLS] BusinessRAGService()=%.3fs", time.monotonic() - _t)

    def _consulta(operation: str, handler) -> dict:
        return run_consulta(actor_level, actor_user_id, operation, handler)

    def _execucao(operation: str, intent: str, handler) -> dict:
        return run_execucao(actor_level, actor_user_id, operation, intent, handler)

    # --- resolvedores de entidade (apresentação) ---

    def _list_frentes_servico() -> list[dict]:
        try:
            return _frente_svc.listar_frentes(tenant_id)
        except Exception:
            return []

    def _list_obras() -> list[dict]:
        try:
            return _obra_svc.listar_obras(tenant_id)
        except Exception:
            return []

    def _build_frentes_by_id() -> dict[int, str]:
        mapping: dict[int, str] = {}
        for item in _list_frentes_servico():
            item_id = item.get("id")
            item_nome = item.get("nome")
            if isinstance(item_id, int) and isinstance(item_nome, str) and item_nome.strip():
                mapping[item_id] = item_nome.strip()
        return mapping

    def _resolve_obra_selection(obra_id: int | None = None, obra: str | None = None) -> dict:
        if obra_id is not None:
            return {"ok": True, "obra_id": int(obra_id)}
        if not obra:
            return {"ok": True, "obra_id": None}
        items = _list_obras()
        if not items:
            return {"ok": False, "message": "Nao foi possivel resolver obra no momento.", "next_steps": ["tentar novamente"]}
        target = normalize_text(obra)
        exact = [i for i in items if normalize_text(str(i.get("nome") or "")) == target]
        exact_code = [i for i in items if normalize_text(str(i.get("codigo") or "")) == target]
        candidates = exact or exact_code
        if len(candidates) == 1:
            return {"ok": True, "obra_id": int(candidates[0]["id"])}
        partial = [i for i in items if target in normalize_text(str(i.get("nome") or ""))]
        if len(partial) == 1:
            return {"ok": True, "obra_id": int(partial[0]["id"])}
        source = candidates if len(candidates) > 1 else partial
        if source:
            options = [str(i.get("nome") or "").strip() for i in source[:8] if str(i.get("nome") or "").strip()]
            return {"ok": False, "message": f"Nome de obra ambiguo. Opcoes: {', '.join(options)}", "opcoes": options, "next_steps": ["pedir ao usuario para escolher"]}
        options = [str(i.get("nome") or "").strip() for i in items[:8] if str(i.get("nome") or "").strip()]
        return {"ok": False, "message": f"Obra nao encontrada para '{obra}'. Opcoes: {', '.join(options)}.", "opcoes": options, "next_steps": ["pedir nome exato"]}

    def _resolve_frente_servico_selection(frente_servico_nome: str | None) -> dict:
        if not frente_servico_nome:
            return {"ok": True, "frente_servico_id": None}
        items = _list_frentes_servico()
        if not items:
            return {"ok": False, "message": "Nao foi possivel resolver frente de servico no momento.", "next_steps": ["tentar novamente"]}
        target = normalize_text(frente_servico_nome)
        exact = [i for i in items if normalize_text(str(i.get("nome") or "")) == target]
        if len(exact) == 1:
            return {"ok": True, "frente_servico_id": exact[0]["id"]}
        partial = [i for i in items if target in normalize_text(str(i.get("nome") or ""))]
        candidates = exact or partial
        if len(candidates) == 1:
            return {"ok": True, "frente_servico_id": candidates[0]["id"]}
        if len(candidates) > 1:
            options = [str(i.get("nome") or "").strip() for i in candidates[:8] if str(i.get("nome") or "").strip()]
            return {"ok": False, "message": f"Nome de frente ambiguo. Opcoes: {', '.join(options)}", "opcoes": options, "next_steps": ["pedir escolha"]}
        options = [str(i.get("nome") or "").strip() for i in items[:8] if str(i.get("nome") or "").strip()]
        return {"ok": False, "message": f"Frente nao encontrada para '{frente_servico_nome}'. Opcoes: {', '.join(options)}.", "opcoes": options, "next_steps": ["pedir nome exato"]}

    def _resolve_alert_identifier(codigo_alerta: str | None = None, alert_id: str | None = None) -> dict:
        if alert_id:
            return {"ok": True, "alert_id": str(alert_id), "alert_code": codigo_alerta}
        if not codigo_alerta:
            return {"ok": False, "message": "Informe codigo_alerta ou alert_id.", "next_steps": ["pedir o codigo do alerta"]}
        return {"ok": True, "alert_code": str(codigo_alerta).strip(), "alert_id": alert_id}

    # =========================================================================
    # TOOLS DE CONSULTA
    # =========================================================================
    _t_consulta = time.monotonic()
    logger.info("[GATEWAY_TOOLS] iniciando definição das tools de consulta")

    @tool
    def consultar_diario_obra(data: str, frente_servico: str | None = None) -> dict:
        """Consulta diario de obra de um dia por linguagem de negocio (data e nome da frente)."""
        data_normalizada = parse_iso_date(data, "data").isoformat()

        def handler() -> dict:
            resolved = _resolve_frente_servico_selection(frente_servico)
            if not resolved.get("ok"):
                return resolved
            result = _registro_svc.consultar_diario_dia(
                tenant_id, actor_user_id, actor_level,
                data=data_normalizada,
                frente_servico_id=resolved.get("frente_servico_id"),
            )
            raw = result if isinstance(result, dict) else {"resultado": result}
            mapped = map_consultar_diario_obra_output(
                raw,
                frentes_by_id=_build_frentes_by_id(),
                requested_frente_nome=frente_servico or None,
            )
            payload = strip_technical_keys(mapped)
            payload["tenant_id"] = tenant_id
            return payload

        return _consulta("consultar_diario_obra", handler)

    @tool
    def listar_frentes_servico_operacional() -> dict:
        """Lista frentes de servico em linguagem de negocio para apoiar cadastro e filtros."""

        def handler() -> dict:
            items = _frente_svc.listar_frentes(tenant_id)
            return {"ok": True, "total": len(items), "frentes_servico": strip_technical_keys(items)}

        return _consulta("listar_frentes_servico_operacional", handler)

    @tool
    def consultar_frente_servico_operacional(frente_id: int | None = None, nome: str | None = None) -> dict:
        """Consulta uma frente de servico especifica pelo ID numerico ou pelo nome."""

        def handler() -> dict:
            result = _frente_svc.obter_frente(tenant_id, frente_id=frente_id, nome=nome)
            return strip_technical_keys(result) if isinstance(result, dict) else result

        return _consulta("consultar_frente_servico_operacional", handler)

    @tool
    def listar_obras_operacional() -> dict:
        """Lista obras em linguagem de negocio para vinculacao de registros e alertas."""

        def handler() -> dict:
            items = _obra_svc.listar_obras(tenant_id)
            return {"ok": True, "total": len(items), "obras": strip_technical_keys(items)}

        return _consulta("listar_obras_operacional", handler)

    @tool
    def listar_registros_operacional(
        data: str | None = None,
        frente_servico: str | None = None,
        obra_id: int | None = None,
        usuario_id: int | None = None,
        status: str | None = None,
        limite: int = 50,
    ) -> dict:
        """Lista registros de producao com filtros por data, frente, obra, usuario e status."""

        def handler() -> dict:
            frente_id = None
            if frente_servico:
                resolved = _resolve_frente_servico_selection(frente_servico)
                if not resolved.get("ok"):
                    return resolved
                frente_id = resolved.get("frente_servico_id")
            result = _registro_svc.listar_registros(
                tenant_id, actor_user_id, actor_level,
                data=data,
                frente_servico_id=frente_id,
                obra_id=obra_id,
                usuario_id=usuario_id,
                limit=max(1, min(int(limite), 200)),
            )
            return {"ok": True, "total": len(result), "registros": strip_technical_keys(result)}

        return _consulta("listar_registros_operacional", handler)

    @tool
    def consultar_producao_periodo(
        data_inicio: str,
        data_fim: str,
        frente_servico: str | None = None,
        apenas_impraticaveis: bool = False,
        usuario_id: int | None = None,
    ) -> dict:
        """Consulta producao e resumo por periodo, com opcao de filtro por frente e dias impraticaveis."""
        data_inicio_norm = parse_iso_date(data_inicio, "data_inicio").isoformat()
        data_fim_norm = parse_iso_date(data_fim, "data_fim").isoformat()

        def handler() -> dict:
            resolved = _resolve_frente_servico_selection(frente_servico)
            if not resolved.get("ok"):
                return resolved
            result = _registro_svc.consultar_diario_periodo(
                tenant_id, actor_user_id, actor_level,
                data_inicio=data_inicio_norm,
                data_fim=data_fim_norm,
                frente_servico_id=resolved.get("frente_servico_id"),
                usuario_id=usuario_id,
                apenas_impraticaveis=bool(apenas_impraticaveis),
            )
            raw = result if isinstance(result, dict) else {"resultado": result}
            mapped = map_consultar_producao_periodo_output(raw, frentes_by_id=_build_frentes_by_id())
            payload = strip_technical_keys(mapped)
            payload["tenant_id"] = tenant_id
            return payload

        return _consulta("consultar_producao_periodo", handler)

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

        def handler() -> dict:
            resolved_obra = _resolve_obra_selection(obra_id=obra_id, obra=obra)
            if not resolved_obra.get("ok"):
                return resolved_obra
            result = _alerta_svc.listar_alertas(
                tenant_id, actor_user_id, actor_level,
                status=status,
                severity=severidade,
                obra_id=resolved_obra.get("obra_id"),
                apenas_nao_lidos=bool(apenas_nao_lidos),
                limit=max(1, min(int(limite), 200)),
            )
            return strip_technical_keys(map_consultar_alertas_operacionais_output(result))

        return _consulta("consultar_alertas_operacionais", handler)

    @tool
    def consultar_alerta_operacional(codigo_alerta: str | None = None, alert_id: str | None = None) -> dict:
        """Consulta um alerta operacional especifico por codigo de negocio ou UUID."""

        def handler() -> dict:
            resolved = _resolve_alert_identifier(codigo_alerta=codigo_alerta, alert_id=alert_id)
            if not resolved.get("ok"):
                return resolved
            result = _alerta_svc.obter_alerta(
                tenant_id, actor_user_id, actor_level,
                alert_id=resolved.get("alert_id"),
                alert_code=resolved.get("alert_code"),
            )
            if isinstance(result, dict):
                alerta_raw = result.get("alerta", result)
                return {"ok": True, "alerta": map_alerta_to_business(alerta_raw) if isinstance(alerta_raw, dict) else alerta_raw}
            return {"ok": True, "alerta": {"resultado": result}}

        return _consulta("consultar_alerta_operacional", handler)

    @tool
    def consultar_registro_operacional(registro_id: int) -> dict:
        """Consulta um registro de producao diaria pelo ID numerico."""

        def handler() -> dict:
            result = _registro_svc.obter_registro(tenant_id, actor_user_id, actor_level, int(registro_id))
            if not isinstance(result, dict) or not result.get("ok"):
                return result
            registro_raw = result.get("registro", result)
            frente_nome = None
            frente_id = registro_raw.get("frente_servico_id")
            if isinstance(frente_id, int):
                frente_nome = _build_frentes_by_id().get(frente_id)
            return {"ok": True, "registro": map_registro_to_business(registro_raw, frente_nome=frente_nome)}

        return _consulta("consultar_registro_operacional", handler)

    @tool
    def listar_tipos_alerta_operacional(ativos_apenas: bool = False) -> dict:
        """Lista aliases de tipos de alerta e os tipos canonicos disponiveis."""

        def handler() -> dict:
            result = _alert_type_svc.listar_tipos_alerta(tenant_id, actor_level, ativos_apenas=bool(ativos_apenas))
            return strip_technical_keys(result) if isinstance(result, dict) else result

        return _consulta("listar_tipos_alerta_operacional", handler)

    @tool
    def consultar_tipo_alerta_operacional(tipo_id: str | None = None, alias: str | None = None) -> dict:
        """Consulta um tipo de alerta cadastrado por UUID tecnico ou alias de negocio."""

        def handler() -> dict:
            result = _alert_type_svc.obter_tipo_alerta(tenant_id, actor_level, tipo_id=tipo_id, alias=alias)
            return strip_technical_keys(result) if isinstance(result, dict) else result

        return _consulta("consultar_tipo_alerta_operacional", handler)

    @tool
    def consultar_padroes_operacionais(pergunta: str, k: int = 3) -> dict:
        """Consulta base de conhecimento operacional dedicada no estilo encarregado."""

        def handler() -> dict:
            return business_rag.consultar_padroes_operacionais(pergunta=pergunta, k=k)

        return _consulta("consultar_padroes_operacionais", handler)

    @tool
    def consultar_schema_frente_servico(frente_servico: str) -> dict:
        """Retorna os campos obrigatorios, opcionais e extras do schema de registro vinculado a frente de servico."""

        def handler() -> dict:
            return business_rag.consultar_schema_frente(frente_servico=frente_servico, tenant_id=tenant_id)

        return _consulta("consultar_schema_frente_servico", handler)

    @tool
    def sugerir_campos_faltantes(tipo_registro: str, dados_parciais: dict) -> dict:
        """Sugere campos obrigatorios faltantes para completar registro operacional."""

        def handler() -> dict:
            return business_rag.sugerir_campos_faltantes(
                tipo_registro=tipo_registro,
                dados_parciais=dados_parciais or {},
                tenant_id=tenant_id,
                obra_id_ativa=obra_id_ativa,
            )

        return _consulta("sugerir_campos_faltantes", handler)

    logger.info("[GATEWAY_TOOLS] tools de consulta definidas=%.3fs", time.monotonic() - _t_consulta)

    # =========================================================================
    # TOOLS DE EXECUÇÃO
    # =========================================================================
    _t_execucao = time.monotonic()
    logger.info("[GATEWAY_TOOLS] iniciando definição das tools de execução")

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
        resultado: float | None = None,
        tempo_manha: str | None = None,
        tempo_tarde: str | None = None,
        observacao: str | None = None,
        campos_extras_valores: dict | None = None,
        lado_pista: str | None = None,
        confirmado: bool = False,
        intencao: str | None = "registrar_producao",
    ) -> dict:
        """Executa registro de producao diaria sem exigir confirmacao explicita."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="registrar_producao")
        data_normalizada = parse_iso_date(data, "data").isoformat()

        def handler() -> dict:
            resolved_obra = _resolve_obra_selection(obra_id=obra_id, obra=obra)
            if not resolved_obra.get("ok"):
                return resolved_obra
            resolved_frente = _resolve_frente_servico_selection(frente_servico)
            if not resolved_frente.get("ok"):
                return resolved_frente

            result = _registro_svc.criar_registro(
                tenant_id, actor_user_id, actor_level,
                data=data_normalizada,
                obra_id=resolved_obra.get("obra_id"),
                frente_servico_id=resolved_frente.get("frente_servico_id"),
                estaca_inicial=estaca_inicial,
                estaca_final=estaca_final,
                km_inicial=km_inicial,
                km_final=km_final,
                local_descritivo=local_descritivo,
                localizacao=localizacao,
                resultado=resultado,
                tempo_manha=tempo_manha,
                tempo_tarde=tempo_tarde,
                observacao=observacao,
                campos_extras_valores=campos_extras_valores,
                lado_pista=lado_pista,
            )

            schema_ctx = business_rag.sugerir_campos_faltantes(
                tipo_registro="producao_diaria",
                dados_parciais={
                    "data": data_normalizada,
                    "frente_servico_id": resolved_frente.get("frente_servico_id"),
                    "frente_servico": frente_servico,
                    "resultado": resultado,
                    "tempo_manha": tempo_manha,
                    "tempo_tarde": tempo_tarde,
                    "lado_pista": lado_pista,
                    "observacao": observacao,
                },
                tenant_id=tenant_id,
            )
            return {
                "registro": result if isinstance(result, dict) else {"resultado": result},
                "tenant_id": tenant_id,
                "campos_pendentes_schema": schema_ctx.get("faltantes", []) if schema_ctx.get("ok") else [],
                "campos_extras_schema": schema_ctx.get("campos_extras", []),
            }

        return _execucao("registrar_producao_diaria", intent, handler)

    @tool
    def registrar_alerta_operacional(
        tipo_alerta: str,
        obra_id: int | None = None,
        obra: str | None = None,
        titulo: str | None = None,
        descricao: str | None = None,
        severidade: str | None = None,
        local: str | None = None,
        equipamento: str | None = None,
        confirmado: bool = False,
        intencao: str | None = "registrar_alerta",
    ) -> dict:
        """Executa abertura de alerta operacional sem exigir confirmacao explicita."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="registrar_alerta")

        def handler() -> dict:
            alert_type = _normalize_alert_type_for_gateway(tipo_alerta)
            resolved_obra = _resolve_obra_selection(obra_id=obra_id, obra=obra)
            if not resolved_obra.get("ok"):
                return resolved_obra
            result = _alerta_svc.criar_alerta(
                tenant_id, actor_user_id, actor_level,
                type=alert_type,
                title=titulo,
                description=descricao,
                severity=severidade,
                obra_id=resolved_obra.get("obra_id"),
                location_detail=local,
                equipment_name=equipamento,
            )
            if isinstance(result, dict):
                alerta_raw = result.get("alerta", result)
                return {"ok": True, "alerta": map_alerta_to_business(alerta_raw) if isinstance(alerta_raw, dict) else alerta_raw}
            return {"alerta": {"resultado": result}}

        return _execucao("registrar_alerta_operacional", intent, handler)

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
        intencao: str | None = "registrar_alerta",
    ) -> dict:
        """Atualiza status e demais campos de um alerta operacional por codigo de negocio ou UUID."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="registrar_alerta")

        def handler() -> dict:
            resolved = _resolve_alert_identifier(codigo_alerta=codigo_alerta, alert_id=alert_id)
            if not resolved.get("ok"):
                return resolved
            resolved_obra = _resolve_obra_selection(obra_id=obra_id, obra=obra)
            if not resolved_obra.get("ok"):
                return resolved_obra
            result = _alerta_svc.atualizar_alerta(
                tenant_id, actor_user_id, actor_level,
                alert_id=resolved.get("alert_id"),
                alert_code=resolved.get("alert_code"),
                status=status,
                resolution_notes=observacoes_resolucao,
                type=_normalize_alert_type_for_gateway(tipo_alerta) if tipo_alerta else None,
                severity=severidade,
                obra_id=resolved_obra.get("obra_id"),
                title=titulo,
                description=descricao,
                location_detail=local,
                equipment_name=equipamento,
                photo_urls=fotos,
                priority_score=prioridade,
                notified_channels=canais_notificados,
            )
            if isinstance(result, dict):
                alerta_raw = result.get("alerta", result)
                return {"ok": True, "alerta": map_alerta_to_business(alerta_raw) if isinstance(alerta_raw, dict) else alerta_raw}
            return {"ok": True, "alerta": {"resultado": result}}

        return _execucao("atualizar_alerta_operacional", intent, handler)

    @tool
    def marcar_alerta_como_lido_operacional(
        codigo_alerta: str | None = None,
        alert_id: str | None = None,
        intencao: str | None = "registrar_alerta",
    ) -> dict:
        """Marca um alerta operacional como lido por codigo de negocio ou UUID."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="registrar_alerta")

        def handler() -> dict:
            resolved = _resolve_alert_identifier(codigo_alerta=codigo_alerta, alert_id=alert_id)
            if not resolved.get("ok"):
                return resolved
            result = _alerta_svc.marcar_alerta_lido(
                tenant_id, actor_user_id, actor_level,
                alert_id=resolved.get("alert_id"),
                alert_code=resolved.get("alert_code"),
            )
            return strip_technical_keys(result) if isinstance(result, dict) else {"ok": True, "resultado": result}

        return _execucao("marcar_alerta_como_lido_operacional", intent, handler)

    @tool
    def marcar_alerta_como_nao_lido_operacional(
        codigo_alerta: str | None = None,
        alert_id: str | None = None,
        intencao: str | None = "registrar_alerta",
    ) -> dict:
        """Marca um alerta operacional como nao lido por codigo de negocio ou UUID."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="registrar_alerta")

        def handler() -> dict:
            resolved = _resolve_alert_identifier(codigo_alerta=codigo_alerta, alert_id=alert_id)
            if not resolved.get("ok"):
                return resolved
            result = _alerta_svc.marcar_alerta_nao_lido(
                tenant_id, actor_user_id, actor_level,
                alert_id=resolved.get("alert_id"),
                alert_code=resolved.get("alert_code"),
            )
            return strip_technical_keys(result) if isinstance(result, dict) else {"ok": True, "resultado": result}

        return _execucao("marcar_alerta_como_nao_lido_operacional", intent, handler)

    @tool
    def deletar_alerta_operacional(
        codigo_alerta: str | None = None,
        alert_id: str | None = None,
        confirmado: bool = False,
        intencao: str | None = "registrar_alerta",
    ) -> dict:
        """Remove um alerta operacional por codigo de negocio ou UUID."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="registrar_alerta")

        def handler() -> dict:
            resolved = _resolve_alert_identifier(codigo_alerta=codigo_alerta, alert_id=alert_id)
            if not resolved.get("ok"):
                return resolved
            result = _alerta_svc.deletar_alerta(
                tenant_id, actor_user_id, actor_level,
                alert_id=resolved.get("alert_id"),
                alert_code=resolved.get("alert_code"),
            )
            return strip_technical_keys(result) if isinstance(result, dict) else {"ok": bool(result)}

        return _execucao("deletar_alerta_operacional", intent, handler)

    @tool
    def atualizar_status_registro_operacional(
        registro_id: int,
        status: str,
        confirmado: bool = False,
        intencao: str | None = "atualizar_registro",
    ) -> dict:
        """Atualiza status do registro sem exigir confirmacao explicita no gateway."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="atualizar_registro")

        def handler() -> dict:
            result = _registro_svc.atualizar_status_registro(
                tenant_id, actor_user_id, actor_level, int(registro_id), status
            )
            if isinstance(result, dict):
                return strip_technical_keys({"registro": result.get("registro", result)})
            return strip_technical_keys({"registro": {"resultado": result}})

        return _execucao("atualizar_status_registro_operacional", intent, handler)

    @tool
    def anexar_imagem_registro_operacional(
        registro_id: int,
        imagem_url: str,
        confirmado: bool = False,
        intencao: str | None = "atualizar_registro",
    ) -> dict:
        """Anexa imagem (URL externa) a um registro operacional, incluindo registros aprovados."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="atualizar_registro")

        def handler() -> dict:
            result = _registro_svc.anexar_imagem_registro(
                tenant_id, actor_user_id, actor_level, int(registro_id), imagem_url
            )
            return strip_technical_keys(result) if isinstance(result, dict) else {"ok": True, "resultado": result}

        return _execucao("anexar_imagem_registro_operacional", intent, handler)

    @tool
    def gerar_diario_obra(
        obra_id: int | None = None,
        obra_nome: str | None = None,
        tipo_periodo: str = "diario",
        data_inicio: str | None = None,
        data_fim: str | None = None,
        motivo_regeracao: str | None = None,
        intencao: str | None = "gerar_diario",
    ) -> dict:
        """Gera ou regera o diario de obra para um periodo. Use quando o engenheiro solicitar o diario via chat."""
        from datetime import date as _date
        import unicodedata

        def _norm(s: str) -> str:
            return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()

        obra_id_resolvido = obra_id or obra_id_ativa

        if obra_id_resolvido is None and obra_nome:
            obras = _list_obras()
            query = _norm(obra_nome)
            candidatos = [o for o in obras if query in _norm(str(o.get("nome") or ""))]
            if len(candidatos) == 1:
                obra_id_resolvido = candidatos[0]["id"]
            elif len(candidatos) > 1:
                nomes = [o.get("nome") for o in candidatos]
                return {"ok": False, "message": f"Encontrei {len(candidatos)} obras com '{obra_nome}': {nomes}. Qual delas?", "next_steps": ["pedir escolha pelo nome exato"]}
            else:
                obras_disponiveis = [o.get("nome") for o in obras]
                return {"ok": False, "message": f"Obra '{obra_nome}' não encontrada. Disponíveis: {obras_disponiveis}.", "next_steps": ["apresentar lista e pedir escolha"]}

        if obra_id_resolvido is None:
            obras = _list_obras()
            if not obras:
                return {"ok": False, "message": "Nenhuma obra disponível para este usuário."}
            if len(obras) == 1:
                obra_id_resolvido = obras[0]["id"]
            else:
                nomes = [o.get("nome") for o in obras]
                return {"ok": False, "message": "Nenhuma obra ativa no contexto. Qual obra você deseja?", "obras_disponiveis": nomes, "next_steps": ["apresentar lista e pedir escolha"]}

        today = _date.today().isoformat()
        data_inicio_norm = parse_iso_date(data_inicio or today, "data_inicio").isoformat()

        if data_fim:
            data_fim_norm = parse_iso_date(data_fim, "data_fim").isoformat()
        elif tipo_periodo == "semanal":
            from datetime import timedelta
            data_fim_norm = (_date.fromisoformat(data_inicio_norm) + timedelta(days=6)).isoformat()
        elif tipo_periodo == "mensal":
            import calendar
            inicio = _date.fromisoformat(data_inicio_norm)
            ultimo_dia = calendar.monthrange(inicio.year, inicio.month)[1]
            data_fim_norm = inicio.replace(day=ultimo_dia).isoformat()
        else:
            data_fim_norm = data_inicio_norm

        intent = GatewayPolicyService.normalize_intent(intencao, default="gerar_diario")

        def handler() -> dict:
            if tenant_id is None:
                return {"ok": False, "message": "tenant_id nao disponivel no contexto."}
            try:
                from backend.services.diario_service import gerar_ou_regerar_diario
                from datetime import date as _d
                result = gerar_ou_regerar_diario(
                    obra_id=int(obra_id_resolvido),
                    tenant_id=int(tenant_id),
                    tipo=tipo_periodo,
                    data_inicio=_d.fromisoformat(data_inicio_norm),
                    data_fim=_d.fromisoformat(data_fim_norm),
                    gerado_por=int(actor_user_id),
                    motivo_regeracao=motivo_regeracao,
                )
                versao_url = result["versoes"][0].get("storage_url") if result.get("versoes") else None
                return {
                    "ok": True,
                    "diario_id": result.get("id"),
                    "versao_atual": result.get("versao_atual"),
                    "status": result.get("status"),
                    "periodo": f"{result.get('data_inicio')} a {result.get('data_fim')}",
                    "url_pdf": versao_url,
                    "message": (
                        f"Diário {'gerado' if result.get('versao_atual') == 1 else 'regerado'} com sucesso. "
                        f"Versão {result.get('versao_atual')}."
                        + (f" PDF disponível em: {versao_url}" if versao_url else "")
                    ),
                }
            except (ValueError, RuntimeError) as exc:
                return {"ok": False, "message": str(exc)}

        return _execucao("gerar_diario_obra", intent, handler)

    @tool
    def criar_tipo_alerta_operacional(
        alias: str,
        tipo_canonico: str,
        descricao: str | None = None,
        ativo: bool = True,
        confirmado: bool = False,
        intencao: str | None = "gerenciar_tipo_alerta",
    ) -> dict:
        """Cria alias de tipo de alerta para mapear linguagem de negocio para tipo canonico."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="gerenciar_tipo_alerta")

        def handler() -> dict:
            result = _alert_type_svc.criar_tipo_alerta(
                tenant_id, actor_user_id, actor_level,
                alias=alias,
                tipo_canonico=tipo_canonico,
                descricao=descricao,
                ativo=bool(ativo),
            )
            return strip_technical_keys(result) if isinstance(result, dict) else {"ok": True, "resultado": result}

        return _execucao("criar_tipo_alerta_operacional", intent, handler)

    @tool
    def atualizar_tipo_alerta_operacional(
        tipo_id: str | None = None,
        alias: str | None = None,
        novo_alias: str | None = None,
        tipo_canonico: str | None = None,
        descricao: str | None = None,
        ativo: bool | None = None,
        confirmado: bool = False,
        intencao: str | None = "gerenciar_tipo_alerta",
    ) -> dict:
        """Atualiza alias, tipo canonico, descricao ou status de um tipo de alerta."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="gerenciar_tipo_alerta")

        def handler() -> dict:
            result = _alert_type_svc.atualizar_tipo_alerta(
                tenant_id, actor_user_id, actor_level,
                tipo_id=tipo_id,
                alias=alias,
                novo_alias=novo_alias,
                tipo_canonico=tipo_canonico,
                descricao=descricao,
                ativo=ativo,
            )
            return strip_technical_keys(result) if isinstance(result, dict) else {"ok": True, "resultado": result}

        return _execucao("atualizar_tipo_alerta_operacional", intent, handler)

    @tool
    def deletar_tipo_alerta_operacional(
        tipo_id: str | None = None,
        alias: str | None = None,
        confirmado: bool = False,
        intencao: str | None = "gerenciar_tipo_alerta",
    ) -> dict:
        """Remove alias de tipo de alerta cadastrado."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="gerenciar_tipo_alerta")

        def handler() -> dict:
            result = _alert_type_svc.deletar_tipo_alerta(
                tenant_id, actor_level, tipo_id=tipo_id, alias=alias
            )
            return strip_technical_keys(result) if isinstance(result, dict) else {"ok": bool(result)}

        return _execucao("deletar_tipo_alerta_operacional", intent, handler)

    @tool
    def criar_obra_operacional(
        nome: str,
        codigo: str | None = None,
        descricao: str | None = None,
        ativo: bool = True,
        tipo_obra: str | None = None,
        tipo_obra_id: int | None = None,
        intencao: str | None = "gerenciar_frente_servico",
    ) -> dict:
        """Cria obra operacional no tenant atual."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="gerenciar_frente_servico")

        def handler() -> dict:
            result = _obra_svc.criar_obra(
                tenant_id, actor_level,
                nome=nome, codigo=codigo, descricao=descricao,
                ativo=bool(ativo), tipo_obra=tipo_obra, tipo_obra_id=tipo_obra_id,
            )
            return {"ok": True, "obra": strip_technical_keys(result.get("obra", result))} if isinstance(result, dict) else {"ok": True, "resultado": result}

        return _execucao("criar_obra_operacional", intent, handler)

    @tool
    def atualizar_obra_operacional(
        obra_id: int,
        nome: str | None = None,
        codigo: str | None = None,
        descricao: str | None = None,
        ativo: bool | None = None,
        intencao: str | None = "gerenciar_frente_servico",
    ) -> dict:
        """Atualiza obra operacional."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="gerenciar_frente_servico")

        def handler() -> dict:
            result = _obra_svc.atualizar_obra(
                tenant_id, actor_level, int(obra_id),
                nome=nome, codigo=codigo, descricao=descricao, ativo=ativo,
            )
            return strip_technical_keys(result) if isinstance(result, dict) else {"ok": True, "resultado": result}

        return _execucao("atualizar_obra_operacional", intent, handler)

    @tool
    def deletar_obra_operacional(
        obra_id: int,
        intencao: str | None = "gerenciar_frente_servico",
    ) -> dict:
        """Remove obra operacional."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="gerenciar_frente_servico")

        def handler() -> dict:
            result = _obra_svc.deletar_obra(tenant_id, actor_level, int(obra_id))
            return strip_technical_keys(result) if isinstance(result, dict) else {"ok": bool(result)}

        return _execucao("deletar_obra_operacional", intent, handler)

    @tool
    def atualizar_registro_operacional(
        registro_id: int,
        data: str | None = None,
        frente_servico: str | None = None,
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
        status: str | None = None,
        campos_extras_valores: dict | None = None,
        intencao: str | None = "atualizar_registro",
    ) -> dict:
        """Atualiza dados de um registro de producao existente."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="atualizar_registro")

        def handler() -> dict:
            frente_id = None
            if frente_servico:
                resolved = _resolve_frente_servico_selection(frente_servico)
                if not resolved.get("ok"):
                    return resolved
                frente_id = resolved.get("frente_servico_id")
            resolved_obra = _resolve_obra_selection(obra_id=obra_id, obra=obra)
            if not resolved_obra.get("ok"):
                return resolved_obra
            result = _registro_svc.atualizar_registro(
                tenant_id, actor_user_id, actor_level, int(registro_id),
                data=data,
                frente_servico_id=frente_id,
                obra_id=resolved_obra.get("obra_id"),
                estaca_inicial=estaca_inicial,
                estaca_final=estaca_final,
                km_inicial=km_inicial,
                km_final=km_final,
                local_descritivo=local_descritivo,
                localizacao=localizacao,
                tempo_manha=tempo_manha,
                tempo_tarde=tempo_tarde,
                observacao=observacao,
                lado_pista=lado_pista,
                status=status,
                campos_extras_valores=campos_extras_valores,
            )
            return strip_technical_keys(result) if isinstance(result, dict) else {"ok": True, "resultado": result}

        return _execucao("atualizar_registro_operacional", intent, handler)

    @tool
    def deletar_registro_operacional(
        registro_id: int,
        intencao: str | None = "atualizar_registro",
    ) -> dict:
        """Remove um registro de producao diaria pelo ID."""
        intent = GatewayPolicyService.normalize_intent(intencao, default="atualizar_registro")

        def handler() -> dict:
            result = _registro_svc.deletar_registro(tenant_id, actor_user_id, actor_level, int(registro_id))
            return strip_technical_keys(result) if isinstance(result, dict) else {"ok": bool(result)}

        return _execucao("deletar_registro_operacional", intent, handler)

    logger.info("[GATEWAY_TOOLS] tools de execução definidas=%.3fs", time.monotonic() - _t_execucao)
    logger.info("[GATEWAY_TOOLS] get_gateway_tools: total=%.3fs", time.monotonic() - _t0)
    return [
        consultar_diario_obra,
        listar_frentes_servico_operacional,
        consultar_frente_servico_operacional,
        listar_obras_operacional,
        listar_registros_operacional,
        consultar_producao_periodo,
        consultar_alertas_operacionais,
        consultar_alerta_operacional,
        consultar_registro_operacional,
        listar_tipos_alerta_operacional,
        consultar_tipo_alerta_operacional,
        consultar_padroes_operacionais,
        consultar_schema_frente_servico,
        sugerir_campos_faltantes,
        registrar_producao_diaria,
        registrar_alerta_operacional,
        atualizar_alerta_operacional,
        marcar_alerta_como_lido_operacional,
        marcar_alerta_como_nao_lido_operacional,
        deletar_alerta_operacional,
        atualizar_status_registro_operacional,
        anexar_imagem_registro_operacional,
        gerar_diario_obra,
        criar_tipo_alerta_operacional,
        atualizar_tipo_alerta_operacional,
        deletar_tipo_alerta_operacional,
        criar_obra_operacional,
        atualizar_obra_operacional,
        deletar_obra_operacional,
        atualizar_registro_operacional,
        deletar_registro_operacional,
    ]
