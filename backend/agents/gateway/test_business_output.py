import unittest

from backend.agents.gateway.contracts import ActorContext, GatewayRequest, GatewayRequestMeta
from backend.agents.gateway.errors import GatewayValidationError
from backend.agents.gateway.gateway_service import GatewayService
from backend.agents.gateway.mappers import (
    has_technical_keys,
    map_consultar_alertas_operacionais_output,
    map_consultar_diario_obra_output,
    map_consultar_producao_periodo_output,
)
from backend.agents.tools import gateway_tools as gateway_tools_module
from backend.agents.tools.database.common import resolve_frente_servico_id
from backend.db.repository import Repository


class GatewayBusinessOutputTests(unittest.TestCase):
    def test_consultar_diario_output_has_no_technical_keys(self):
        raw = {
            "ok": True,
            "diario": {
                "data": "2026-04-14",
                "total_resultado": 120.5,
                "total_registros": 2,
                "dias_impraticaveis": False,
                "resumo_clima": "Manha: limpo | Tarde: nublado",
                "registros": [
                    {
                        "id": 10,
                        "frente_servico_id": 7,
                        "usuario_registrador_id": 3,
                        "data": "2026-04-14",
                        "estaca_inicial": 1.0,
                        "estaca_final": 2.0,
                        "resultado": 1.0,
                        "tempo_manha": "limpo",
                        "tempo_tarde": "nublado",
                        "observacao": "ok",
                        "pista": "direito",
                    }
                ],
            },
        }

        mapped = map_consultar_diario_obra_output(raw, frentes_by_id={7: "Terraplenagem"})

        self.assertTrue(mapped.get("ok"))
        self.assertFalse(has_technical_keys(mapped))

    def test_consultar_periodo_output_has_no_technical_keys(self):
        raw = {
            "ok": True,
            "relatorio": {
                "data_inicio": "2026-04-01",
                "data_fim": "2026-04-14",
                "total_resultado_periodo": 200.0,
                "total_dias": 2,
                "total_dias_impraticaveis": 0,
                "media_diaria": 100.0,
                "dias": [
                    {
                        "data": "2026-04-14",
                        "total_resultado": 120.5,
                        "total_registros": 2,
                        "dias_impraticaveis": False,
                        "resumo_clima": "Manha: limpo | Tarde: nublado",
                        "registros": [
                            {"frente_servico_id": 7, "resultado": 100.0},
                            {"frente_servico_id": 9, "resultado": 20.5},
                        ],
                    }
                ],
            },
        }

        mapped = map_consultar_producao_periodo_output(raw, frentes_by_id={7: "Terraplenagem", 9: "Drenagem"})

        self.assertTrue(mapped.get("ok"))
        self.assertFalse(has_technical_keys(mapped))

    def test_consultar_alertas_output_has_no_technical_keys(self):
        raw = {
            "ok": True,
            "total": 1,
            "alertas": [
                {
                    "id": "abc",
                    "code": "ALT-2026-0001",
                    "type": "falta_material",
                    "severity": "alta",
                    "status": "aberto",
                    "description": "Faltou brita",
                    "location_detail": "KM 12",
                    "reported_by": 2,
                    "read_by": 3,
                    "created_at": "2026-04-14T08:00:00",
                }
            ],
        }

        mapped = map_consultar_alertas_operacionais_output(raw)

        self.assertTrue(mapped.get("ok"))
        self.assertFalse(has_technical_keys(mapped))

    def test_ambiguity_message_does_not_expose_ids(self):
        original_listar = Repository.frentes_servico.listar

        class _FakeFrente:
            def __init__(self, frente_id: int, nome: str):
                self.id = frente_id
                self.nome = nome

        try:
            Repository.frentes_servico.listar = lambda db: [
                _FakeFrente(1, "Terraplenagem Norte"),
                _FakeFrente(2, "Terraplenagem Sul"),
            ]

            with self.assertRaises(ValueError) as ctx:
                resolve_frente_servico_id(db=None, frente_servico_nome="Terraplenagem")

            message = str(ctx.exception)
            self.assertIn("Opções:", message)
            self.assertNotIn("id=", message)
            self.assertNotRegex(message.lower(), r"\bid\b")
        finally:
            Repository.frentes_servico.listar = original_listar

    def test_gateway_tool_ambiguity_returns_clarification_payload_without_ids(self):
        original_get_database_tools = gateway_tools_module.get_database_tools

        class _FakeTool:
            def __init__(self, name, handler):
                self.name = name
                self._handler = handler

            def invoke(self, args):
                return self._handler(args)

        def _build_fake_tools(actor_user_id: int, actor_level: str):
            del actor_user_id
            del actor_level
            return [
                _FakeTool(
                    "listar_frentes_servico",
                    lambda args: [
                        {"id": 1, "nome": "Terraplenagem Norte"},
                        {"id": 2, "nome": "Terraplenagem Sul"},
                    ],
                ),
                _FakeTool("consultar_diario_dia", lambda args: {"ok": True, "diario": {"registros": []}}),
            ]

        try:
            gateway_tools_module.get_database_tools = _build_fake_tools
            tools = gateway_tools_module.get_gateway_tools(actor_user_id=1, actor_level="encarregado")
            consultar = next(tool for tool in tools if tool.name == "consultar_diario_obra")

            response = consultar.invoke({"data": "2026-04-14", "frente_servico": "Terraplenagem"})

            self.assertFalse(response.get("ok"))
            self.assertIn("Opcoes:", response.get("message", ""))
            self.assertIn("next_steps", response)
            self.assertNotIn("id=", response.get("message", ""))
            self.assertNotRegex(response.get("message", "").lower(), r"\bid\b")
        finally:
            gateway_tools_module.get_database_tools = original_get_database_tools

    def test_atualizar_status_registro_gateway_no_technical_ids(self):
        original_get_database_tools = gateway_tools_module.get_database_tools

        class _FakeTool:
            def __init__(self, name, handler):
                self.name = name
                self._handler = handler

            def invoke(self, args):
                return self._handler(args)

        def _build_fake_tools(actor_user_id: int, actor_level: str):
            del actor_user_id
            del actor_level
            return [
                _FakeTool(
                    "atualizar_status_registro",
                    lambda args: {
                        "ok": True,
                        "registro": {
                            "id": args.get("registro_id"),
                            "status": args.get("status"),
                        },
                    },
                ),
            ]

        try:
            gateway_tools_module.get_database_tools = _build_fake_tools
            tools = gateway_tools_module.get_gateway_tools(actor_user_id=1, actor_level="encarregado")
            atualizar_status = next(tool for tool in tools if tool.name == "atualizar_status_registro_operacional")

            response = atualizar_status.invoke(
                {
                    "registro_id": 321,
                    "status": "consolidado",
                    "confirmado": True,
                }
            )

            self.assertTrue(response.get("ok"))
            self.assertFalse(has_technical_keys(response))
            self.assertEqual(response.get("registro", {}).get("status"), "consolidado")
        finally:
            gateway_tools_module.get_database_tools = original_get_database_tools

    def test_gateway_service_maps_value_error_to_validation_error(self):
        service = GatewayService()
        request = GatewayRequest(
            actor=ActorContext(actor_user_id=1, actor_level="encarregado"),
            meta=GatewayRequestMeta(operation="op_teste", action_route="consulta"),
            payload={},
        )

        with self.assertRaises(GatewayValidationError) as ctx:
            service.execute_consulta(request, lambda req: (_ for _ in ()).throw(ValueError("entrada invalida")))

        exc = ctx.exception
        self.assertEqual(exc.status_code, 422)
        self.assertEqual(exc.code, "gateway_validation_error")
        self.assertIn("entrada invalida", exc.message)

    def test_frente_not_found_message_guides_user_to_business_name(self):
        original_get_database_tools = gateway_tools_module.get_database_tools

        class _FakeTool:
            def __init__(self, name, handler):
                self.name = name
                self._handler = handler

            def invoke(self, args):
                return self._handler(args)

        def _build_fake_tools(actor_user_id: int, actor_level: str):
            del actor_user_id
            del actor_level
            return [
                _FakeTool(
                    "listar_frentes_servico",
                    lambda args: [
                        {"id": 1, "nome": "Drenagem"},
                        {"id": 2, "nome": "Pavimentacao A"},
                        {"id": 3, "nome": "Terraplanagem"},
                    ],
                ),
                _FakeTool("criar_registro", lambda args: {"ok": True, "registro": {}}),
            ]

        try:
            gateway_tools_module.get_database_tools = _build_fake_tools
            tools = gateway_tools_module.get_gateway_tools(actor_user_id=1, actor_level="encarregado")
            criar = next(tool for tool in tools if tool.name == "registrar_producao_diaria")

            response = criar.invoke(
                {
                    "data": "2026-04-14",
                    "frente_servico": "CAUCAIA - TRECHO DA PARADA DE ONIBUS",
                    "estaca_inicial": 0.0,
                    "estaca_final": 1.0,
                    "tempo_manha": "limpo",
                    "tempo_tarde": "limpo",
                    "confirmado": True,
                }
            )

            self.assertFalse(response.get("ok"))
            self.assertIn("Use o nome da frente de servico", response.get("message", ""))
            self.assertIn("Opcoes cadastradas", response.get("message", ""))
            self.assertIn("pode cadastrar a frente de servico", response.get("message", ""))
        finally:
            gateway_tools_module.get_database_tools = original_get_database_tools

    def test_write_tools_return_confirmation_needed_without_raising(self):
        original_get_database_tools = gateway_tools_module.get_database_tools

        class _FakeTool:
            def __init__(self, name, handler):
                self.name = name
                self._handler = handler

            def invoke(self, args):
                return self._handler(args)

        def _build_fake_tools(actor_user_id: int, actor_level: str):
            del actor_user_id
            del actor_level
            return [
                _FakeTool(
                    "listar_frentes_servico",
                    lambda args: [{"id": 1, "nome": "Terraplenagem Norte"}],
                ),
                _FakeTool("criar_registro", lambda args: {"ok": True, "registro": {"id": 1}}),
            ]

        try:
            gateway_tools_module.get_database_tools = _build_fake_tools
            tools = gateway_tools_module.get_gateway_tools(actor_user_id=1, actor_level="encarregado")
            registrar = next(tool for tool in tools if tool.name == "registrar_producao_diaria")

            response = registrar.invoke(
                {
                    "data": "2026-04-14",
                    "frente_servico": "Terraplenagem Norte",
                    "estaca_inicial": 0.0,
                    "estaca_final": 1.0,
                    "tempo_manha": "limpo",
                    "tempo_tarde": "limpo",
                    "confirmado": False,
                }
            )

            self.assertTrue(response.get("ok"))
            self.assertIn("registro", response)
        finally:
            gateway_tools_module.get_database_tools = original_get_database_tools


if __name__ == "__main__":
    unittest.main()
