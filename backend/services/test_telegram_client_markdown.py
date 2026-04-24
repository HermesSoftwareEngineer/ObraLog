import unittest
from unittest.mock import Mock, patch

from telegram.constants import ParseMode

from backend.services.telegram_client import (
    _build_markdown_candidates,
    _sanitize_markdown_for_telegram,
)


class TelegramMarkdownSanitizerTests(unittest.TestCase):
    def test_replaces_leading_asterisk_bullets(self):
        raw = "*   *Registrar Produção:* item\n*   *Consultar Diário:* item"

        out = _sanitize_markdown_for_telegram(raw)

        self.assertIn("• *Registrar Produção:* item", out)
        self.assertIn("• *Consultar Diário:* item", out)
        self.assertNotIn("*   *Registrar", out)

    def test_escapes_unbalanced_asterisk(self):
        raw = "Texto com *asterisco sem fechamento"

        out = _sanitize_markdown_for_telegram(raw)

        self.assertIn(r"\*asterisco", out)

    def test_keeps_balanced_simple_markdown(self):
        raw = "*negrito* e _italico_ e `codigo`"

        out = _sanitize_markdown_for_telegram(raw)

        self.assertEqual(raw, out)

    def test_build_candidates_prioritizes_library_markdown_v2(self):
        lib = Mock()
        lib.markdownify.return_value = "*negrito*"

        with patch("backend.services.telegram_client.telegramify_markdown", lib):
            candidates = _build_markdown_candidates("**negrito**")

        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(candidates[0][0], "*negrito*")
        self.assertEqual(candidates[0][1], ParseMode.MARKDOWN_V2)
        self.assertEqual(candidates[0][2], "library_markdown_v2")

    def test_build_candidates_without_library_keeps_markdown_and_sanitized(self):
        with patch("backend.services.telegram_client.telegramify_markdown", None):
            candidates = _build_markdown_candidates("*   *Titulo:* ok")

        self.assertEqual(candidates[0][1], ParseMode.MARKDOWN)
        self.assertEqual(candidates[0][2], "raw_markdown")
        self.assertTrue(any(c[2] == "sanitized_markdown" for c in candidates))


if __name__ == "__main__":
    unittest.main()
