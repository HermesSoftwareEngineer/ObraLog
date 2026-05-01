import tempfile
import unittest
from pathlib import Path

from backend.agents.gateway import rag_service as rag_service_module
from backend.agents.gateway.rag_service import BusinessRAGService
from backend.db.repository import Repository


class BusinessRAGUserInstructionsTests(unittest.TestCase):
    def test_load_blocks_includes_editable_user_instructions(self):
        original_reader = rag_service_module.read_agent_instructions

        with tempfile.TemporaryDirectory() as temp_dir:
            knowledge_file = Path(temp_dir) / "knowledge.md"
            knowledge_file.write_text(
                "## Procedimento\nUsar checklist de campo antes de registrar.",
                encoding="utf-8",
            )

            try:
                rag_service_module.read_agent_instructions = lambda: "Sempre validar clima e frente antes de confirmar."
                service = BusinessRAGService(knowledge_path=knowledge_file)
                response = service.consultar_padroes_operacionais("validar clima frente", k=4)
            finally:
                rag_service_module.read_agent_instructions = original_reader

        self.assertTrue(response.get("ok"))
        itens = response.get("itens", [])
        self.assertTrue(any("Instrucoes Operacionais Editaveis do Usuario" in item for item in itens))
        self.assertTrue(any("validar clima" in item.lower() for item in itens))

    def test_sugerir_campos_faltantes_valida_frente_e_usuario_existentes(self):
        original_frentes_listar = Repository.frentes_servico.listar
        original_frentes_obter = Repository.frentes_servico.obter_por_id
        original_usuarios_obter = Repository.usuarios.obter_por_id

        class _FakeFrente:
            def __init__(self, frente_id: int, nome: str):
                self.id = frente_id
                self.nome = nome

        class _FakeUsuario:
            def __init__(self, usuario_id: int):
                self.id = usuario_id

        try:
            Repository.frentes_servico.listar = lambda db: [_FakeFrente(1, "Terraplenagem Norte")]
            Repository.frentes_servico.obter_por_id = lambda db, frente_id: _FakeFrente(frente_id, "Terraplenagem Norte") if frente_id == 1 else None
            Repository.usuarios.obter_por_id = lambda db, usuario_id: _FakeUsuario(usuario_id) if usuario_id == 7 else None

            service = BusinessRAGService()
            response = service.sugerir_campos_faltantes(
                "producao_diaria",
                {
                    "data": "2026-04-14",
                    "frente_servico_id": 99,
                    "usuario_registrador_id": 7,
                    "estaca_inicial": 0.0,
                    "estaca_final": 10.0,
                    "tempo_manha": "limpo",
                    "tempo_tarde": "limpo",
                },
            )

            self.assertTrue(response.get("ok"))
            self.assertEqual(response.get("faltantes"), [])
            self.assertFalse(response.get("pronto_para_consolidar"))
            self.assertTrue(response.get("validacoes"))
            self.assertEqual(response.get("validacoes")[0].get("campo"), "frente_servico_id")
            self.assertEqual(response.get("validacoes")[0].get("status"), "inexistente")
        finally:
            Repository.frentes_servico.listar = original_frentes_listar
            Repository.frentes_servico.obter_por_id = original_frentes_obter
            Repository.usuarios.obter_por_id = original_usuarios_obter

    def test_sugerir_campos_faltantes_usa_perfil_localizacao_km(self):
        service = BusinessRAGService()
        response = service.sugerir_campos_faltantes(
            "producao_diaria",
            {
                "data": "2026-04-14",
                "frente_servico": "Frente X",
                "tempo_manha": "limpo",
                "tempo_tarde": "limpo",
            },
            tenant_id=99,
            obra_id_ativa=123,
            location_profile="km",
        )

        self.assertTrue(response.get("ok"))
        self.assertEqual(response.get("perfil_localizacao"), "km")
        self.assertIn("tipo_localizacao", response.get("obrigatorios", []))
        self.assertIn("tipo_localizacao", response.get("faltantes", []))

    def test_sugerir_campos_faltantes_infer_texto_por_local_descritivo(self):
        service = BusinessRAGService()
        response = service.sugerir_campos_faltantes(
            "producao_diaria",
            {
                "data": "2026-05-01",
                "frente_servico": "Drenagem",
                "tempo_manha": "limpo",
                "tempo_tarde": "limpo",
                "local_descritivo": "Armazem",
            },
            location_profile="estaca",
        )

        self.assertTrue(response.get("ok"))
        self.assertEqual(response.get("perfil_localizacao"), "texto")
        self.assertNotIn("estaca_inicial", response.get("faltantes", []))
        self.assertNotIn("estaca_final", response.get("faltantes", []))


if __name__ == "__main__":
    unittest.main()
