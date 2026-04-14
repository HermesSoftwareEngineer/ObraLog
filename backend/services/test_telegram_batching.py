import unittest
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


if __name__ == "__main__":
    unittest.main()
