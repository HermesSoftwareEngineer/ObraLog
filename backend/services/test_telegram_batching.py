import unittest
from unittest.mock import MagicMock
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

    def test_image_update_is_buffered_and_not_processed_immediately(self):
        update = {
            "message": {
                "chat": {"id": 77},
                "message_thread_id": 11,
                "photo": [{"file_id": "abc"}],
            }
        }

        with patch.object(telegram, "_image_batcher") as batcher, patch.object(
            telegram.bot_client, "send_typing"
        ) as send_typing, patch.object(telegram, "_processor") as processor:
            batcher.enqueue.return_value = 2
            result = telegram.handle_telegram_update(update)

        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("buffered"))
        self.assertEqual(result.get("reason"), "image_batch_queued")
        self.assertEqual(result.get("pending_images"), 2)
        batcher.enqueue.assert_called_once_with(update)
        send_typing.assert_not_called()
        processor.process.assert_not_called()

    def test_image_debouncer_restarts_timer_and_flushes_single_batch(self):
        processor = MagicMock()
        created_timers = []

        class _FakeTimer:
            def __init__(self, _interval, func, args=None, kwargs=None):
                self.func = func
                self.args = args or ()
                self.kwargs = kwargs or {}
                self.cancel_called = False
                self.daemon = False

            def start(self):
                return None

            def cancel(self):
                self.cancel_called = True

        def _fake_timer_factory(interval, func, args=None, kwargs=None):
            timer = _FakeTimer(interval, func, args=args, kwargs=kwargs)
            created_timers.append(timer)
            return timer

        first_update = {
            "message": {"chat": {"id": 90}, "photo": [{"file_id": "img-1"}]}
        }
        second_update = {
            "message": {"chat": {"id": 90}, "photo": [{"file_id": "img-2"}]}
        }

        with patch("backend.services.telegram.threading.Timer", side_effect=_fake_timer_factory):
            debouncer = telegram._ImageBatchDebouncer(processor=processor, wait_seconds=0.5)
            debouncer.enqueue(first_update)
            debouncer.enqueue(second_update)

            self.assertEqual(len(created_timers), 2)
            self.assertTrue(created_timers[0].cancel_called)

            # Fire only the latest timer callback: it should process both images together.
            created_timers[-1].func(*created_timers[-1].args, **created_timers[-1].kwargs)

        processor.process.assert_called_once_with([first_update, second_update])


if __name__ == "__main__":
    unittest.main()
