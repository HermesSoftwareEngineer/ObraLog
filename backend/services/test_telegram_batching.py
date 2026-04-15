import unittest
import logging
from unittest.mock import patch

from backend.services import telegram


class _FakeTimer:
    def __init__(self, interval, function, args=None, kwargs=None):
        self.interval = interval
        self.function = function
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.daemon = False
        self.started = False
        self.canceled = False

    def cancel(self):
        self.canceled = True

    def start(self):
        self.started = True


class TelegramBatchingTests(unittest.TestCase):
    def setUp(self):
        telegram._MESSAGE_BATCH_PENDING.clear()
        telegram._MESSAGE_BATCH_TIMERS.clear()

    def tearDown(self):
        telegram._MESSAGE_BATCH_PENDING.clear()
        telegram._MESSAGE_BATCH_TIMERS.clear()

    def test_enqueue_groups_same_chat_and_replaces_timer(self):
        created_timers = []

        def fake_timer_factory(interval, function, args=None, kwargs=None):
            timer = _FakeTimer(interval, function, args=args, kwargs=kwargs)
            created_timers.append(timer)
            return timer

        update_1 = {"update_id": 1001, "message": {"chat": {"id": 77}, "text": "primeira"}}
        update_2 = {"update_id": 1002, "message": {"chat": {"id": 77}, "text": "segunda"}}

        with patch("backend.services.telegram.threading.Timer", side_effect=fake_timer_factory):
            result_1 = telegram._enqueue_update_for_batch(update_1)
            result_2 = telegram._enqueue_update_for_batch(update_2)

        self.assertTrue(result_1.get("ok"))
        self.assertTrue(result_2.get("queued"))
        self.assertEqual(len(created_timers), 2)
        self.assertTrue(created_timers[0].canceled)
        self.assertTrue(created_timers[1].started)
        self.assertEqual(len(telegram._MESSAGE_BATCH_PENDING.get("77", [])), 2)

    def test_flush_processes_single_batch_once(self):
        processed_batches = []

        update_1 = {"update_id": 1, "message": {"chat": {"id": 88}, "text": "a"}}
        update_2 = {"update_id": 2, "message": {"chat": {"id": 88}, "text": "b"}}

        telegram._MESSAGE_BATCH_PENDING["88"] = [update_1, update_2]
        telegram._MESSAGE_BATCH_TIMERS["88"] = _FakeTimer(1.0, lambda: None)

        with patch("backend.services.telegram._process_telegram_message_batch", side_effect=lambda updates: processed_batches.append(updates)):
            telegram._flush_queued_updates("88")

        self.assertEqual(len(processed_batches), 1)
        self.assertEqual(len(processed_batches[0]), 2)
        self.assertNotIn("88", telegram._MESSAGE_BATCH_PENDING)
        self.assertNotIn("88", telegram._MESSAGE_BATCH_TIMERS)

    def test_handle_poll_answer_bypasses_batch_queue(self):
        update = {"poll_answer": {"poll_id": "poll-1", "option_ids": []}}

        with patch("backend.services.telegram._handle_poll_answer_update", return_value={"ok": True, "reason": "poll"}) as handle_poll, patch(
            "backend.services.telegram._enqueue_update_for_batch"
        ) as enqueue:
            result = telegram.handle_telegram_update(update)

        self.assertEqual(result.get("reason"), "poll")
        handle_poll.assert_called_once()
        enqueue.assert_not_called()

    def test_edited_message_is_ignored_before_queue(self):
        update = {"edited_message": {"chat": {"id": 99}, "text": "texto editado"}}

        result = telegram.handle_telegram_update(update)

        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("ignored"))
        self.assertEqual(result.get("reason"), "edited_message_ignored")
        self.assertNotIn("99", telegram._MESSAGE_BATCH_PENDING)

    def test_hash_is_stable_for_same_message_id(self):
        hash_a = telegram._build_message_hash(chat_id=77, message_id=456, update_id=1)
        hash_b = telegram._build_message_hash(chat_id=77, message_id=456, update_id=999)

        self.assertEqual(hash_a, hash_b)

    def test_hash_uses_update_id_when_message_id_missing(self):
        hash_a = telegram._build_message_hash(chat_id=77, message_id=None, update_id=1)
        hash_b = telegram._build_message_hash(chat_id=77, message_id=None, update_id=2)

        self.assertNotEqual(hash_a, hash_b)

    def test_polling_debug_env_disabled_by_default(self):
        with patch.dict("os.environ", {}, clear=False):
            self.assertFalse(telegram._is_polling_debug_enabled())

    def test_polling_debug_env_enabled(self):
        with patch.dict("os.environ", {"TELEGRAM_POLLING_DEBUG": "true"}, clear=False):
            self.assertTrue(telegram._is_polling_debug_enabled())

    def test_configure_polling_debug_logging_sets_info_when_disabled(self):
        with patch.dict("os.environ", {"TELEGRAM_POLLING_DEBUG": "false"}, clear=False), patch("backend.services.telegram.logging.getLogger") as get_logger:
            logger_mock = get_logger.return_value
            telegram._configure_polling_debug_logging()

        logger_mock.setLevel.assert_any_call(logging.INFO)

    def test_configure_polling_debug_logging_sets_debug_when_enabled(self):
        with patch.dict("os.environ", {"TELEGRAM_POLLING_DEBUG": "1"}, clear=False), patch("backend.services.telegram.logging.getLogger") as get_logger:
            logger_mock = get_logger.return_value
            telegram._configure_polling_debug_logging()

        logger_mock.setLevel.assert_any_call(logging.DEBUG)

    def test_typing_indicator_env_enabled_default_true(self):
        with patch.dict("os.environ", {}, clear=False):
            self.assertTrue(telegram._is_typing_indicator_enabled())

    def test_typing_indicator_interval_from_env(self):
        with patch.dict("os.environ", {"TELEGRAM_TYPING_INTERVAL_SECONDS": "4.2"}, clear=False):
            self.assertEqual(telegram._typing_indicator_interval_seconds(), 4.2)

    def test_send_typing_uses_send_chat_action(self):
        with patch("backend.services.telegram._run_async_sync") as run_async:
            telegram.send_typing(chat_id=77, message_thread_id=11)

        run_async.assert_called_once_with(
            telegram._telegram_api_call_async,
            "send_chat_action",
            chat_id=77,
            action="typing",
            message_thread_id=11,
        )

    def test_handle_update_sends_typing_immediately_when_enabled(self):
        update = {
            "message": {
                "chat": {"id": 77},
                "message_thread_id": 11,
                "text": "oi",
            }
        }

        with patch.dict("os.environ", {"TELEGRAM_TYPING_INDICATOR_ENABLED": "true"}, clear=False), patch(
            "backend.services.telegram.send_typing"
        ) as send_typing, patch("backend.services.telegram._enqueue_update_for_batch", return_value={"ok": True}):
            telegram.handle_telegram_update(update)

        send_typing.assert_called_once_with(chat_id=77, message_thread_id=11)

    def test_handle_update_does_not_send_typing_when_disabled(self):
        update = {"message": {"chat": {"id": 77}, "text": "oi"}}

        with patch.dict("os.environ", {"TELEGRAM_TYPING_INDICATOR_ENABLED": "false"}, clear=False), patch(
            "backend.services.telegram.send_typing"
        ) as send_typing, patch("backend.services.telegram._enqueue_update_for_batch", return_value={"ok": True}):
            telegram.handle_telegram_update(update)

        send_typing.assert_not_called()

    def test_send_immediate_typing_for_update_returns_true_when_sent(self):
        update = {"message": {"chat": {"id": 77}, "message_thread_id": 11, "text": "oi"}}

        with patch.dict("os.environ", {"TELEGRAM_TYPING_INDICATOR_ENABLED": "true"}, clear=False), patch(
            "backend.services.telegram.send_typing"
        ) as send_typing:
            sent = telegram._send_immediate_typing_for_update(update)

        self.assertTrue(sent)
        send_typing.assert_called_once_with(chat_id=77, message_thread_id=11)

    def test_handle_update_skips_typing_when_already_sent(self):
        update = {"message": {"chat": {"id": 77}, "text": "oi"}}

        with patch("backend.services.telegram.send_typing") as send_typing, patch(
            "backend.services.telegram._enqueue_update_for_batch", return_value={"ok": True}
        ):
            telegram.handle_telegram_update(update, typing_already_sent=True)

        send_typing.assert_not_called()

    def test_start_typing_indicator_disabled_returns_noop(self):
        with patch.dict("os.environ", {"TELEGRAM_TYPING_INDICATOR_ENABLED": "false"}, clear=False), patch(
            "backend.services.telegram.threading.Thread"
        ) as thread_cls:
            stop = telegram._start_typing_indicator(chat_id=77)
            stop()

        thread_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
