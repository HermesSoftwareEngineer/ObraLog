import unittest
from unittest.mock import patch

from backend.agents.gateway.errors import GatewayValidationError
from backend.agents.gateway.mappers import parse_iso_date
from backend.agents.tools.gateway_tools import _normalize_execution_intent
from backend.agents.tools.gateway_tools import _requires_confirmation_for_status_change
from backend.agents.tools.gateway_tools import get_gateway_tools


class _FakeInternalTool:
    def __init__(self, name: str, result):
        self.name = name
        self._result = result

    def invoke(self, _args: dict):
        return self._result


class _CaptureInternalTool:
    def __init__(self, name: str, handler):
        self.name = name
        self._handler = handler
        self.calls: list[dict] = []

    def invoke(self, args: dict):
        self.calls.append(dict(args))
        return self._handler(args)


class GatewayIntentNormalizationTests(unittest.TestCase):
    def test_parse_iso_date_accepts_dd_mm_yyyy(self):
        parsed = parse_iso_date("01/05/2026", "data")
        self.assertEqual(parsed.isoformat(), "2026-05-01")

    def test_parse_iso_date_rejects_unknown_format(self):
        with self.assertRaises(GatewayValidationError):
            parse_iso_date("01-05-2026", "data")

    def test_alias_criar_parcial_maps_to_registrar_producao(self):
        resolved = _normalize_execution_intent("criar_parcial", default="registrar_producao")
        self.assertEqual(resolved, "registrar_producao")

    def test_unknown_intent_falls_back_to_default(self):
        resolved = _normalize_execution_intent("qualquer_coisa", default="atualizar_registro")
        self.assertEqual(resolved, "atualizar_registro")

    def test_valid_intent_is_kept(self):
        resolved = _normalize_execution_intent("consolidar_registro", default="registrar_producao")
        self.assertEqual(resolved, "consolidar_registro")

    def test_gateway_exposes_anexar_imagem_tool(self):
        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="encarregado")
        tool_names = {tool.name for tool in tools}
        self.assertIn("anexar_imagem_registro_operacional", tool_names)

    def test_gateway_exposes_frente_crud_tools(self):
        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="encarregado")
        tool_names = {tool.name for tool in tools}
        self.assertIn("listar_frentes_servico_operacional", tool_names)
        self.assertIn("criar_frente_servico_operacional", tool_names)
        self.assertIn("atualizar_frente_servico_operacional", tool_names)
        self.assertIn("deletar_frente_servico_operacional", tool_names)

    def test_gateway_exposes_alert_crud_tools(self):
        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="encarregado")
        tool_names = {tool.name for tool in tools}
        self.assertIn("consultar_alertas_operacionais", tool_names)
        self.assertIn("consultar_alerta_operacional", tool_names)
        self.assertIn("registrar_alerta_operacional", tool_names)
        self.assertIn("atualizar_alerta_operacional", tool_names)
        self.assertIn("deletar_alerta_operacional", tool_names)
        self.assertIn("marcar_alerta_como_lido_operacional", tool_names)
        self.assertIn("marcar_alerta_como_nao_lido_operacional", tool_names)

    def test_gateway_exposes_alert_type_crud_tools(self):
        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="encarregado")
        tool_names = {tool.name for tool in tools}
        self.assertIn("listar_tipos_alerta_operacional", tool_names)
        self.assertIn("consultar_tipo_alerta_operacional", tool_names)
        self.assertIn("criar_tipo_alerta_operacional", tool_names)
        self.assertIn("atualizar_tipo_alerta_operacional", tool_names)
        self.assertIn("deletar_tipo_alerta_operacional", tool_names)

    def test_requires_confirmation_is_disabled_for_status_updates(self):
        self.assertFalse(_requires_confirmation_for_status_change("consolidado", intent="atualizar_registro"))
        self.assertFalse(_requires_confirmation_for_status_change("revisado", intent="atualizar_registro"))

    def test_anexar_imagem_without_confirmation_executes(self):
        fake_attach = _FakeInternalTool(
            "anexar_imagem_registro",
            {
                "ok": True,
                "imagem": {"id": 1, "registro_id": 10, "external_url": "https://img.test/a.jpg"},
            },
        )

        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[fake_attach]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="encarregado")

        anexar_tool = next(tool for tool in tools if tool.name == "anexar_imagem_registro_operacional")
        result = anexar_tool.invoke({"registro_id": 10, "imagem_url": "https://img.test/a.jpg", "confirmado": False})

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("operation"), "anexar_imagem_registro_operacional")

    def test_consolidar_status_without_confirmation_executes(self):
        fake_status = _FakeInternalTool(
            "atualizar_status_registro",
            {"ok": True, "registro": {"id": 10, "status": "consolidado"}},
        )

        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[fake_status]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="encarregado")

        status_tool = next(tool for tool in tools if tool.name == "atualizar_status_registro_operacional")
        result = status_tool.invoke({"registro_id": 10, "status": "consolidado", "confirmado": False})

        self.assertTrue(result.get("ok"))
        self.assertEqual(((result.get("registro") or {}).get("status")), "consolidado")

    def test_criar_frente_executes_without_confirmation(self):
        fake_create = _FakeInternalTool(
            "criar_frente_servico",
            {"id": 55, "nome": "Frente Norte", "encarregado_responsavel": None, "observacao": None},
        )

        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[fake_create]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="gerente")

        create_tool = next(tool for tool in tools if tool.name == "criar_frente_servico_operacional")
        result = create_tool.invoke({"nome": "Frente Norte"})

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("operation"), "criar_frente_servico_operacional")
        self.assertEqual((result.get("frente_servico") or {}).get("nome"), "Frente Norte")

    def test_listar_frentes_executes_via_gateway(self):
        fake_list = _FakeInternalTool(
            "listar_frentes_servico",
            [
                {"id": 1, "nome": "Frente A"},
                {"id": 2, "nome": "Frente B"},
            ],
        )

        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[fake_list]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="encarregado")

        list_tool = next(tool for tool in tools if tool.name == "listar_frentes_servico_operacional")
        result = list_tool.invoke({})

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("total"), 2)
        self.assertEqual(result.get("operation"), "listar_frentes_servico_operacional")

    def test_consultar_diario_normalizes_dd_mm_yyyy_before_internal_tool(self):
        fake_list = _FakeInternalTool("listar_frentes_servico", [])
        fake_consultar = _CaptureInternalTool(
            "consultar_diario_dia",
            lambda args: {"ok": True, "diario": {"data": args.get("data"), "registros": []}},
        )

        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[fake_list, fake_consultar]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="encarregado")

        consultar = next(tool for tool in tools if tool.name == "consultar_diario_obra")
        result = consultar.invoke({"data": "01/05/2026"})

        self.assertTrue(result.get("ok"))
        self.assertEqual(fake_consultar.calls[-1].get("data"), "2026-05-01")

    def test_registrar_producao_normalizes_dd_mm_yyyy_before_internal_tool(self):
        fake_list = _FakeInternalTool(
            "listar_frentes_servico",
            [{"id": 9, "nome": "Frente Norte"}],
        )
        fake_create = _CaptureInternalTool(
            "criar_registro",
            lambda args: {"ok": True, "registro": {"data": args.get("data"), "frente_servico_id": args.get("frente_servico_id")}},
        )

        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[fake_list, fake_create]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="encarregado")

        registrar = next(tool for tool in tools if tool.name == "registrar_producao_diaria")
        result = registrar.invoke({"data": "01/05/2026", "frente_servico": "Frente Norte"})

        self.assertTrue(result.get("ok"))
        self.assertEqual(fake_create.calls[-1].get("data"), "2026-05-01")

    def test_registrar_alerta_normalizes_business_type_before_internal_tool(self):
        fake_create_alert = _CaptureInternalTool(
            "criar_alerta",
            lambda args: {"ok": True, "alerta": {"type": args.get("type"), "description": args.get("description")}},
        )

        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[fake_create_alert]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="encarregado")

        alert_tool = next(tool for tool in tools if tool.name == "registrar_alerta_operacional")
        result = alert_tool.invoke(
            {
                "tipo_alerta": "equipamento com defeito",
                "descricao": "Rolo compactador parado",
                "confirmado": False,
            }
        )

        self.assertTrue(result.get("ok"))
        self.assertEqual(fake_create_alert.calls[-1].get("type"), "maquina_quebrada")
        self.assertEqual(((result.get("alerta") or {}).get("tipo")), "maquina_quebrada")

    def test_registrar_alerta_returns_structured_validation_payload_for_unknown_type(self):
        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="encarregado")

        alert_tool = next(tool for tool in tools if tool.name == "registrar_alerta_operacional")
        result = alert_tool.invoke(
            {
                "tipo_alerta": "coisa estranha demais",
                "descricao": "Sem classificacao",
                "confirmado": False,
            }
        )

        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("code"), "gateway_validation_error")
        self.assertIn("tipo_alerta", ((result.get("details") or {}).get("field") or ""))
        self.assertIn("next_steps", result)
        self.assertTrue(any("outro" in step for step in (result.get("next_steps") or [])))

    def test_consultar_alerta_operacional_uses_business_code(self):
        fake_get_alert = _CaptureInternalTool(
            "obter_alerta",
            lambda args: {"ok": True, "alerta": {"code": args.get("alert_code"), "status": "aberto"}},
        )

        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[fake_get_alert]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="encarregado")

        consultar = next(tool for tool in tools if tool.name == "consultar_alerta_operacional")
        result = consultar.invoke({"codigo_alerta": "ALT-2026-0001"})

        self.assertTrue(result.get("ok"))
        self.assertEqual(fake_get_alert.calls[-1].get("alert_code"), "ALT-2026-0001")

    def test_atualizar_alerta_operacional_uses_business_code(self):
        fake_update_alert = _CaptureInternalTool(
            "atualizar_status_alerta",
            lambda args: {"ok": True, "alerta": {"code": args.get("alert_code"), "status": args.get("status")}},
        )

        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[fake_update_alert]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="gerente")

        atualizar = next(tool for tool in tools if tool.name == "atualizar_alerta_operacional")
        result = atualizar.invoke({"codigo_alerta": "ALT-2026-0002", "status": "resolvido"})

        self.assertTrue(result.get("ok"))
        self.assertEqual(fake_update_alert.calls[-1].get("alert_code"), "ALT-2026-0002")
        self.assertEqual(fake_update_alert.calls[-1].get("status"), "resolvido")

    def test_atualizar_alerta_operacional_forwards_additional_fields(self):
        fake_update_alert = _CaptureInternalTool(
            "atualizar_status_alerta",
            lambda args: {"ok": True, "alerta": {"code": args.get("alert_code"), "title": args.get("title")}},
        )

        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[fake_update_alert]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="gerente")

        atualizar = next(tool for tool in tools if tool.name == "atualizar_alerta_operacional")
        result = atualizar.invoke(
            {
                "codigo_alerta": "ALT-2026-0002",
                "titulo": "Novo titulo",
                "descricao": "Nova descricao",
                "severidade": "alta",
                "local": "KM 22",
                "equipamento": "Rolo",
                "fotos": ["https://img.test/1.jpg"],
                "prioridade": 90,
                "canais_notificados": ["telegram"],
            }
        )

        self.assertTrue(result.get("ok"))
        last_call = fake_update_alert.calls[-1]
        self.assertEqual(last_call.get("alert_code"), "ALT-2026-0002")
        self.assertEqual(last_call.get("title"), "Novo titulo")
        self.assertEqual(last_call.get("description"), "Nova descricao")
        self.assertEqual(last_call.get("severity"), "alta")
        self.assertEqual(last_call.get("location_detail"), "KM 22")
        self.assertEqual(last_call.get("equipment_name"), "Rolo")
        self.assertEqual(last_call.get("photo_urls"), ["https://img.test/1.jpg"])
        self.assertEqual(last_call.get("priority_score"), 90)
        self.assertEqual(last_call.get("notified_channels"), ["telegram"])

    def test_deletar_alerta_operacional_uses_business_code(self):
        fake_delete_alert = _CaptureInternalTool(
            "deletar_alerta",
            lambda args: {"ok": True, "message": "Alerta removido com sucesso.", "alert_code": args.get("alert_code")},
        )

        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[fake_delete_alert]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="gerente")

        deletar = next(tool for tool in tools if tool.name == "deletar_alerta_operacional")
        result = deletar.invoke({"codigo_alerta": "ALT-2026-0003"})

        self.assertTrue(result.get("ok"))
        self.assertEqual(fake_delete_alert.calls[-1].get("alert_code"), "ALT-2026-0003")

    def test_gateway_passes_tenant_context_to_database_tools(self):
        captured = {}

        def _fake_get_database_tools(actor_user_id, actor_level, **kwargs):
            captured["actor_user_id"] = actor_user_id
            captured["actor_level"] = actor_level
            captured.update(kwargs)
            return []

        with patch("backend.agents.tools.gateway_tools.get_database_tools", side_effect=_fake_get_database_tools):
            get_gateway_tools(
                actor_user_id=7,
                actor_level="encarregado",
                tenant_id=44,
                obra_id_ativa=901,
                location_profile="km",
            )

        self.assertEqual(captured.get("actor_user_id"), 7)
        self.assertEqual(captured.get("tenant_id"), 44)
        self.assertEqual(captured.get("location_profile"), "km")

    def test_registrar_producao_diaria_km_profile_maps_values(self):
        fake_create = _CaptureInternalTool("criar_registro", lambda args: {"ok": True, "registro": args})
        fake_listar = _FakeInternalTool("listar_frentes_servico", [{"id": 9, "nome": "Frente Oeste"}])

        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[fake_create, fake_listar]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="encarregado", tenant_id=3, location_profile="km")

        registrar = next(tool for tool in tools if tool.name == "registrar_producao_diaria")
        result = registrar.invoke(
            {
                "data": "2026-05-01",
                "frente_servico": "Frente Oeste",
                "km_inicial": 12.5,
                "km_final": 13.0,
                "tempo_manha": "limpo",
                "tempo_tarde": "nublado",
            }
        )

        sent = fake_create.calls[-1]
        self.assertEqual(sent.get("estaca_inicial"), 12.5)
        self.assertEqual(sent.get("estaca_final"), 13.0)
        self.assertEqual((sent.get("localizacao") or {}).get("tipo"), "km")
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("perfil_localizacao"), "km")

    def test_registrar_producao_diaria_text_profile_uses_descriptive_location(self):
        fake_create = _CaptureInternalTool("criar_registro", lambda args: {"ok": True, "registro": args})
        fake_listar = _FakeInternalTool("listar_frentes_servico", [{"id": 2, "nome": "Predial Centro"}])

        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[fake_create, fake_listar]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="encarregado", tenant_id=8, location_profile="texto")

        registrar = next(tool for tool in tools if tool.name == "registrar_producao_diaria")
        registrar.invoke(
            {
                "data": "2026-05-01",
                "frente_servico": "Predial Centro",
                "local_descritivo": "Subsolo bloco B",
                "tempo_manha": "limpo",
                "tempo_tarde": "limpo",
            }
        )

        sent = fake_create.calls[-1]
        self.assertEqual((sent.get("localizacao") or {}).get("detalhe_texto"), "Subsolo bloco B")
        self.assertEqual((sent.get("localizacao") or {}).get("tipo"), "texto")


if __name__ == "__main__":
    unittest.main()
