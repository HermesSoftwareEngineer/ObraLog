import unittest
from unittest.mock import patch

from backend.agents.tools.gateway_tools import _normalize_execution_intent
from backend.agents.tools.gateway_tools import _requires_confirmation_for_status_change
from backend.agents.tools.gateway_tools import get_gateway_tools


class _FakeInternalTool:
    def __init__(self, name: str, result):
        self.name = name
        self._result = result

    def invoke(self, _args: dict):
        return self._result


class GatewayIntentNormalizationTests(unittest.TestCase):
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

    def test_requires_confirmation_only_for_consolidado_status(self):
        self.assertTrue(_requires_confirmation_for_status_change("consolidado", intent="atualizar_registro"))
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

    def test_consolidar_status_without_confirmation_requests_confirmation(self):
        fake_status = _FakeInternalTool(
            "atualizar_status_registro",
            {"ok": True, "registro": {"id": 10, "status": "consolidado"}},
        )

        with patch("backend.agents.tools.gateway_tools.get_database_tools", return_value=[fake_status]):
            tools = get_gateway_tools(actor_user_id=1, actor_level="encarregado")

        status_tool = next(tool for tool in tools if tool.name == "atualizar_status_registro_operacional")
        result = status_tool.invoke({"registro_id": 10, "status": "consolidado", "confirmado": False})

        self.assertFalse(result.get("ok"))
        self.assertIn("confirmacao explicita", str(result.get("message", "")).lower())

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


if __name__ == "__main__":
    unittest.main()
