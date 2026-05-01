import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import IntegrityError

from backend.db.models import ConteudoMensagemTipo
from backend.db.repository import MensagemCampoRepository


class MensagemCampoRepositoryTests(unittest.TestCase):
    def _base_kwargs(self) -> dict:
        return {
            "tenant_id": 1,
            "telegram_chat_id": "1751541108",
            "telegram_message_id": 456,
            "telegram_update_id": 132303124,
            "texto_bruto": "oi, tudo bem?",
            "texto_normalizado": "oi, tudo bem?",
            "payload_json": "{}",
            "hash_idempotencia": "hash-abc",
            "tipo_conteudo": ConteudoMensagemTipo.TEXTO,
            "usuario_id": None,
        }

    def _build_db_mock(self) -> tuple[MagicMock, MagicMock]:
        db = MagicMock()
        query = MagicMock()
        query.filter.return_value = query
        query.first.return_value = None
        db.query.return_value = query
        return db, query

    def test_second_insert_same_chat_message_returns_existing(self):
        db, _ = self._build_db_mock()
        existing = object()

        with patch.object(
            MensagemCampoRepository,
            "_obter_por_chave_natural",
            side_effect=[None, existing],
        ) as natural_lookup:
            first_result = MensagemCampoRepository.criar_telegram(db, **self._base_kwargs())
            second_result = MensagemCampoRepository.criar_telegram(db, **self._base_kwargs())

        self.assertIsNotNone(first_result)
        self.assertIs(second_result, existing)
        self.assertEqual(natural_lookup.call_count, 2)
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_integrity_error_returns_existing_on_fallback_lookup(self):
        db, _ = self._build_db_mock()
        existing_after_race = object()
        db.commit.side_effect = IntegrityError("INSERT", {}, Exception("duplicate"))

        with patch.object(
            MensagemCampoRepository,
            "_obter_por_chave_natural",
            side_effect=[None, existing_after_race],
        ):
            result = MensagemCampoRepository.criar_telegram(db, **self._base_kwargs())

        self.assertIs(result, existing_after_race)
        db.rollback.assert_called_once()
        db.refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
