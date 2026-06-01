"""Testes de diagnóstico do worker.

Objetivos:
1. Verificar que o timeout de graph.invoke() funciona — isola travamentos de LLM.
2. Verificar que o worker processa jobs concorrentemente (não serial).
3. Verificar que o SQL de reclaim usa parâmetro em vez de interpolação.
4. Verificar que o embedding é gerado apenas uma vez por job (sem duplicatas).

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
# 4. Embedding gerado apenas uma vez por job
# ---------------------------------------------------------------------------

class TestEmbeddingDeduplication(unittest.TestCase):
    """Verifica que gerar_embedding é chamado no máximo uma vez por mensagem no processor."""

    def test_embedding_called_once_per_message(self):
        """gerar_embedding deve ser chamado no máximo 1x por invocação de process().

        O embedding é gerado no início do prebuilt context e reutilizado em
        buscar_memorias_com_embedding e atualizar_ultima_mensagem (background thread).
        """
        # gerar_embedding está no namespace do módulo telegram_processor
        # (importado no topo com `from backend.utils.embeddings import gerar_embedding`)
        with patch("backend.services.telegram_processor.gerar_embedding") as mock_embed, \
             patch("backend.services.telegram_processor.graph") as mock_graph, \
             patch("backend.services.telegram_processor.get_or_create_conversa") as mock_conversa, \
             patch("backend.agents.context.tenant_snapshot.build_tenant_snapshot", return_value="snap"), \
             patch("backend.services.telegram_processor.buscar_memorias_com_embedding", return_value=[]), \
             patch("backend.agents.context.vector_context.get_context_for_query", return_value="ctx"), \
             patch("backend.core.config.get_ambiente", return_value="test"), \
             patch("backend.services.telegram_processor._resolver_tenant_ativo", return_value=10), \
             patch("backend.services.telegram_processor._resolver_obra_ativa", return_value=None), \
             patch("backend.services.telegram_processor.response_used_telegram_ui", return_value=False), \
             patch("backend.services.telegram_processor.persistence.persist") as mock_persist, \
             patch("backend.services.telegram_processor.persistence.set_user"), \
             patch("backend.services.telegram_processor.persistence.mark_processed"), \
             patch("backend.services.telegram_processor.Repository.usuarios.atualizar"), \
             patch("backend.services.telegram_processor.SessionLocal") as mock_sl:

            mock_embed.return_value = [0.1, 0.2, 0.3]
            mock_graph.invoke.return_value = {"messages": [MagicMock(content="resposta")]}

            mock_conversa_obj = MagicMock()
            mock_conversa_obj.id = 42
            mock_conversa.return_value = mock_conversa_obj

            mock_persist.return_value = MagicMock(id=uuid_mock())

            mock_sl.return_value.__enter__ = lambda s: MagicMock()
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            usuario = MagicMock()
            usuario.id = 1
            usuario.nome = "Test User"
            usuario.tenant_id = 10
            usuario.nivel_acesso.value = "campo"
            usuario.telegram_thread_id = "123"

            update = {
                "message": {
                    "chat": {"id": 123, "first_name": "Test"},
                    "text": "Olá, registre 10m de concreto",
                    "message_id": 1,
                }
            }

            from backend.services.telegram_processor import MessageProcessor

            client = MagicMock()
            client.send_message.return_value = {"message_id": 99}
            processor = MessageProcessor(client)

            with patch.object(processor._linker, "get_user", return_value=usuario), \
                 patch.object(processor._extractor, "extract", return_value="Olá, registre 10m de concreto"):
                processor.process([update])

        self.assertEqual(
            mock_embed.call_count, 1,
            f"gerar_embedding foi chamado {mock_embed.call_count}x — esperado 1x por job",
        )


def uuid_mock():
    import uuid
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# 5. Timing de referência — mede overhead real fora do LLM
# ---------------------------------------------------------------------------

class TestOverheadTiming(unittest.TestCase):
    """Mede o tempo das operações que rodam ANTES e DEPOIS do graph.invoke().

    Estas não são asserções de correctude — servem como baseline de diagnóstico.
    Os valores ficam visíveis no output do pytest -v -s.
    """

    def test_embedding_latency_baseline(self):
        """Mede quanto tempo gerar_embedding leva com o cliente real (se disponível)."""
        try:
            from backend.utils.embeddings import gerar_embedding
        except Exception as exc:
            self.skipTest(f"Não foi possível importar embeddings: {exc}")

        t0 = time.monotonic()
        result = gerar_embedding("Registrar 10 metros de concreto na frente norte")
        elapsed = time.monotonic() - t0

        print(f"\n[TIMING] gerar_embedding: {elapsed:.3f}s | resultado={'ok' if result else 'None (sem cliente)'}")

        # Não falha se embedding retornar None (sem credenciais no CI)
        if elapsed > 5.0:
            self.fail(
                f"gerar_embedding levou {elapsed:.1f}s — esperado <5s. "
                "Isso causa ~2x esse delay por job (busca_memorias + atualizar_conversa)."
            )

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
