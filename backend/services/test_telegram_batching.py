import unittest
from unittest.mock import patch

from backend.services import telegram


class TelegramDispatchTests(unittest.TestCase):
    def test_handle_poll_answer_bypasses_message_processor(self):
        update = {"poll_answer": {"poll_id": "poll-1", "option_ids": []}}

        with patch.object(telegram, "_poll_handler") as poll_handler, patch.object(
            telegram, "_processor"
        ) as processor:
            poll_handler.handle.return_value = {"ok": True, "reason": "poll"}
            result = telegram.handle_telegram_update(update)

        self.assertEqual(result.get("reason"), "poll")
        poll_handler.handle.assert_called_once_with(update["poll_answer"])
        processor.process.assert_not_called()

    def test_edited_message_is_ignored(self):
        update = {"edited_message": {"chat": {"id": 99}, "text": "texto editado"}}

        result = telegram.handle_telegram_update(update)

        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("ignored"))
        self.assertEqual(result.get("reason"), "edited_message_ignored")

    def test_update_without_chat_id_is_ignored(self):
        update = {"message": {"text": "sem chat"}}

        result = telegram.handle_telegram_update(update)

        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("ignored"))
        self.assertEqual(result.get("reason"), "update_sem_chat_id")

    def test_handle_update_processes_immediately(self):
        update = {
            "message": {
                "chat": {"id": 77},
                "message_thread_id": 11,
                "text": "oi",
            }
        }

        with patch.object(telegram.bot_client, "send_typing") as send_typing, patch.object(
            telegram, "_processor"
        ) as processor:
            processor.process.return_value = {"ok": True, "chat_id": 77}
            result = telegram.handle_telegram_update(update)

        self.assertEqual(result, {"ok": True, "chat_id": 77})
        send_typing.assert_called_once_with(77, 11)
        processor.process.assert_called_once_with([update])

    def test_handle_update_skips_typing_when_already_sent(self):
        update = {"message": {"chat": {"id": 77}, "text": "oi"}}

        with patch.object(telegram.bot_client, "send_typing") as send_typing, patch.object(
            telegram, "_processor"
        ) as processor:
            processor.process.return_value = {"ok": True}
            telegram.handle_telegram_update(update, typing_already_sent=True)

        send_typing.assert_not_called()
        processor.process.assert_called_once_with([update])


if __name__ == "__main__":
    unittest.main()
