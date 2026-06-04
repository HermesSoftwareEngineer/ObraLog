"""Testes de diagnóstico do worker.

Objetivos:
1. Verificar que o timeout de graph.invoke() funciona — isola travamentos de LLM.
2. Verificar que o worker processa jobs concorrentemente (não serial).
3. Verificar que o SQL de reclaim usa parâmetro em vez de interpolação.

Execute com:
    pytest ObraLog/backend/workers/test_worker_diagnostics.py -v
"""
from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(job_id: int = 1, canal: str = "telegram", chat_id: str = "123") -> dict:
    return {"id": job_id, "canal": canal, "chat_id": chat_id, "payload": []}


# ---------------------------------------------------------------------------
# 1. Timeout de graph.invoke()
# ---------------------------------------------------------------------------

class TestGraphInvokeTimeout(unittest.TestCase):
    """Garante que _invoke_with_retry levanta TimeoutError quando o LLM trava."""

    def _make_processor(self):
        from backend.services.telegram_processor import MessageProcessor
        client = MagicMock()
        return MessageProcessor(client)

    @patch("backend.services.telegram_processor._AGENT_INVOKE_TIMEOUT", 0.5)
    @patch("backend.services.telegram_processor.graph")
    def test_timeout_raises_after_deadline(self, mock_graph):
        """graph.invoke() que demora mais que o timeout deve levantar TimeoutError."""
        def _slow_invoke(*args, **kwargs):
            time.sleep(5)  # Simula LLM travado por 5s
            return {}

        mock_graph.invoke.side_effect = _slow_invoke
        processor = self._make_processor()

        config = {"configurable": {"thread_id": "t1"}, "recursion_limit": 14}
        with self.assertRaises(TimeoutError) as ctx:
            processor._invoke_with_retry("teste", config, "123")

        self.assertIn("excedeu", str(ctx.exception))

    @patch("backend.services.telegram_processor._AGENT_INVOKE_TIMEOUT", 5.0)
    @patch("backend.services.telegram_processor.graph")
    def test_fast_invocation_completes_normally(self, mock_graph):
        """graph.invoke() rápido deve retornar sem timeout."""
        mock_graph.invoke.return_value = {"messages": [MagicMock(content="ok")]}
        processor = self._make_processor()

        config = {"configurable": {"thread_id": "t1"}, "recursion_limit": 14}
        result = processor._invoke_with_retry("teste", config, "123")
        self.assertIsNotNone(result)

    @patch("backend.services.telegram_processor._AGENT_INVOKE_TIMEOUT", 2.0)
    @patch("backend.services.telegram_processor.graph")
    def test_timeout_does_not_retry(self, mock_graph):
        """TimeoutError não deve ser retentado — o LLM já está ocupado."""
        call_count = 0

        def _slow_invoke(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            time.sleep(10)
            return {}

        mock_graph.invoke.side_effect = _slow_invoke
        processor = self._make_processor()

        config = {"configurable": {"thread_id": "t1"}, "recursion_limit": 14}
        with self.assertRaises(TimeoutError):
            processor._invoke_with_retry("teste", config, "123")

        # Deve ter tentado apenas 1 vez (sem retry em timeout)
        # Aguarda o join da thread interna para a contagem ser registrada
        time.sleep(0.1)
        self.assertEqual(call_count, 1, "Timeout não deve disparar retry do graph.invoke()")


# ---------------------------------------------------------------------------
# 2. Concorrência do worker
# ---------------------------------------------------------------------------

class TestWorkerConcurrency(unittest.TestCase):
    """Garante que o worker processa múltiplos jobs em paralelo."""

    def test_multiple_jobs_overlap_in_time(self):
        """Dois jobs de 0.3s cada devem terminar em menos de 0.5s no total quando concorrentes."""
        from backend.workers.agent_worker import _run_single_job

        results = []
        lock = threading.Lock()
        barrier = threading.Barrier(2)

        def _fake_process(job):
            barrier.wait(timeout=2)  # Sincroniza para garantir sobreposição
            time.sleep(0.3)
            with lock:
                results.append(job["id"])

        job_a = _make_job(job_id=1)
        job_b = _make_job(job_id=2)

        with patch("backend.workers.agent_worker._process_job", side_effect=_fake_process), \
             patch("backend.workers.agent_worker._mark_done"), \
             patch("backend.workers.agent_worker._mark_error"):

            t_start = time.monotonic()
            t1 = threading.Thread(target=_run_single_job, args=(job_a,))
            t2 = threading.Thread(target=_run_single_job, args=(job_b,))
            t1.start()
            t2.start()
            t1.join(timeout=3)
            t2.join(timeout=3)
            elapsed = time.monotonic() - t_start

        self.assertEqual(sorted(results), [1, 2], "Ambos os jobs devem ter completado")
        self.assertLess(elapsed, 0.7, f"Jobs paralelos devem completar em <0.7s, levou {elapsed:.2f}s")

    @patch("backend.workers.agent_worker.SessionLocal")
    @patch("backend.workers.agent_worker._reclaim_stale_processing_jobs")
    @patch("backend.workers.agent_worker._claim_job")
    @patch("backend.workers.agent_worker._run_single_job")
    def test_worker_respects_concurrency_limit(self, mock_run, mock_claim, mock_reclaim, mock_session):
        """O loop do worker não deve reivindicar mais jobs do que _WORKER_CONCURRENCY."""
        import backend.workers.agent_worker as wmod

        job_counter = [0]
        claimed_at_once = [0]
        max_concurrent = [0]

        original_concurrency = wmod._WORKER_CONCURRENCY
        wmod._WORKER_CONCURRENCY = 2

        def _slow_job(job):
            claimed_at_once[0] += 1
            max_concurrent[0] = max(max_concurrent[0], claimed_at_once[0])
            time.sleep(0.1)
            claimed_at_once[0] -= 1

        mock_run.side_effect = _slow_job

        jobs_issued = [0]

        def _fake_claim(db):
            if jobs_issued[0] >= 4:
                wmod._running = False
                return None
            jobs_issued[0] += 1
            return _make_job(job_id=jobs_issued[0])

        mock_claim.side_effect = _fake_claim
        mock_session.return_value.__enter__ = lambda s: MagicMock()
        mock_session.return_value.__exit__ = MagicMock(return_value=False)

        try:
            wmod._running = True
            wmod.run_worker()
        finally:
            wmod._running = True
            wmod._WORKER_CONCURRENCY = original_concurrency

        self.assertLessEqual(
            max_concurrent[0], 2,
            f"Worker não deveria exceder 2 jobs concorrentes (teve {max_concurrent[0]})",
        )


# ---------------------------------------------------------------------------
# 3. SQL do reclaim (sem interpolação de string)
# ---------------------------------------------------------------------------

class TestReclaimSQL(unittest.TestCase):
    """Garante que o SQL do reclaim usa parâmetros em vez de string replace."""

    def test_reclaim_sql_uses_parameter_binding(self):
        """O SQL de reclaim deve usar :stale_minutes como parâmetro, não string interpolation."""
        import inspect
        from backend.workers.agent_worker import _reclaim_stale_processing_jobs

        src = inspect.getsource(_reclaim_stale_processing_jobs)

        self.assertNotIn(
            ".replace(",
            src,
            "SQL do reclaim não deve usar .replace() para injetar valores",
        )
        self.assertIn(
            "stale_minutes",
            src,
            "SQL do reclaim deve referenciar :stale_minutes como parâmetro",
        )
        # Garante que não há interpolação f-string direta da variável no SQL
        self.assertNotIn(
            "f\"",
            src.split("stale_minutes")[0][-50:],
            "Variável stale_minutes não deve ser interpolada via f-string no SQL",
        )


# ---------------------------------------------------------------------------
# 4. Timing de referência — mede overhead real fora do LLM
# ---------------------------------------------------------------------------

class TestOverheadTiming(unittest.TestCase):
    """Mede o tempo das operações que rodam ANTES e DEPOIS do graph.invoke().

    Estas não são asserções de correctude — servem como baseline de diagnóstico.
    Os valores ficam visíveis no output do pytest -v -s.
    """

    def test_build_system_message_timing_without_prebuilt(self):
        """Mede _build_system_message sem cache — representa o custo do fallback no router."""
        try:
            from backend.agents.nodes.response import _build_system_message
        except Exception as exc:
            self.skipTest(f"Não foi possível importar _build_system_message: {exc}")

        from langchain_core.messages import HumanMessage
        messages = [HumanMessage(content="Teste de timing sem prebuilt")]

        # SessionLocal é importado localmente dentro da função — patch na origem
        with patch("backend.agents.nodes.response.get_context_for_query", return_value=""), \
             patch("backend.db.session.SessionLocal"):

            t0 = time.monotonic()
            try:
                msg = _build_system_message(messages, config=None)
                elapsed = time.monotonic() - t0
                print(f"\n[TIMING] _build_system_message (sem cache): {elapsed:.3f}s")
                self.assertIsNotNone(msg)
            except Exception as exc:
                print(f"\n[TIMING] _build_system_message falhou: {exc}")
                self.skipTest("Falhou na execução — ambiente sem DB/API")


if __name__ == "__main__":
    unittest.main(verbosity=2)
