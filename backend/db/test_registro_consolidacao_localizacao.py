import unittest

from backend.db.repository import RegistroRepository


class RegistroConsolidacaoLocalizacaoTests(unittest.TestCase):
    def test_consolidado_texto_nao_exige_estacas(self):
        payload = {
            "data": "2026-05-01",
            "frente_servico_id": 1,
            "usuario_registrador_id": 10,
            "tempo_manha": "limpo",
            "tempo_tarde": "limpo",
            "metadata_json": {"tipo": "texto"},
            "estaca": "Armazem",
            "estaca_inicial": None,
            "estaca_final": None,
            "resultado": None,
        }

        missing = RegistroRepository._required_missing_for_consolidated(payload)
        self.assertEqual(missing, [])

    def test_consolidado_texto_exige_local_descritivo(self):
        payload = {
            "data": "2026-05-01",
            "frente_servico_id": 1,
            "usuario_registrador_id": 10,
            "tempo_manha": "limpo",
            "tempo_tarde": "limpo",
            "metadata_json": {"tipo": "texto"},
            "estaca": None,
        }

        missing = RegistroRepository._required_missing_for_consolidated(payload)
        self.assertIn("estaca", missing)
        self.assertNotIn("estaca_inicial", missing)
        self.assertNotIn("estaca_final", missing)

    def test_consolidado_estaca_computa_resultado_quando_ausente(self):
        payload = {
            "data": "2026-05-01",
            "frente_servico_id": 1,
            "usuario_registrador_id": 10,
            "tempo_manha": "limpo",
            "tempo_tarde": "limpo",
            "metadata_json": {"tipo": "estaca"},
            "estaca_inicial": 2200.0,
            "estaca_final": 2300.0,
            "resultado": None,
        }

        missing = RegistroRepository._required_missing_for_consolidated(payload)
        self.assertEqual(missing, [])
        self.assertEqual(payload.get("resultado"), 100.0)


if __name__ == "__main__":
    unittest.main()
