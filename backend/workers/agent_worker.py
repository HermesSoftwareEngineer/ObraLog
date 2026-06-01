"""Background worker that processes agent_jobs from the PostgreSQL queue.

Run as a standalone process:
    python -m backend.workers.agent_worker

Uses SELECT ... FOR UPDATE SKIP LOCKED so multiple worker instances can run
in parallel without duplicate processing.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

from sqlalchemy import text

from backend.db.session import SessionLocal

logger = logging.getLogger("obralog.worker.agent")

_ENV = os.environ.get("OBRALOG_ENV", "prod")
_POLL_INTERVAL_SECONDS = float(os.environ.get("AGENT_WORKER_POLL_INTERVAL", "1.0"))
_MAX_ATTEMPTS = int(os.environ.get("AGENT_WORKER_MAX_ATTEMPTS", "3"))
_STALE_JOB_MINUTES = int(os.environ.get("AGENT_WORKER_STALE_JOB_MINUTES", "15"))
# Número de jobs processados em paralelo. Cada slot usa 1 thread e 1 conexão de pool.
_WORKER_CONCURRENCY = int(os.environ.get("AGENT_WORKER_CONCURRENCY", "3"))

_running = True


def _handle_signal(signum, frame):  # noqa: ANN001
    global _running
    logger.info("Worker recebeu sinal %s, encerrando...", signum)
    _running = False


def _reclaim_stale_processing_jobs() -> None:
    """Reseta jobs presos em 'processing' de instâncias anteriores mortas."""
    try:
        with SessionLocal() as db:
            result = db.execute(
                text("""
                    UPDATE agent_jobs
                    SET status     = 'pending',
                        started_at = NULL,
                        attempts   = GREATEST(attempts - 1, 0)
                    WHERE status    = 'processing'
                      AND env       = :env
                      AND started_at < now() - (INTERVAL '1 minute' * :stale_minutes)
                    RETURNING id
                """),
                {"env": _ENV, "stale_minutes": _STALE_JOB_MINUTES},
            )
            reset_ids = [row[0] for row in result]
            db.commit()
        if reset_ids:
            logger.warning(
                "Resetados %d job(s) presos de instâncias anteriores: %s",
                len(reset_ids), reset_ids,
            )
    except Exception as exc:
        logger.error("Falha ao limpar jobs presos: %s", exc)


def _claim_job(db) -> dict | None:
    row = db.execute(
        text("""
            UPDATE agent_jobs
            SET status     = 'processing',
                started_at = now(),
                attempts   = attempts + 1
            WHERE id = (
                SELECT id FROM agent_jobs
                WHERE status   = 'pending'
                  AND attempts < :max_attempts
                  AND env      = :env
                ORDER BY created_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, canal, chat_id, payload
        """),
        {"max_attempts": _MAX_ATTEMPTS, "env": _ENV},
    ).fetchone()
    db.commit()
    return dict(row._mapping) if row else None


def _mark_done(job_id: int) -> None:
    with SessionLocal() as db:
        db.execute(
            text("UPDATE agent_jobs SET status='done', finished_at=now() WHERE id=:id"),
            {"id": job_id},
        )
        db.commit()


def _mark_error(job_id: int, error: str) -> None:
    with SessionLocal() as db:
        db.execute(
            text("""
                UPDATE agent_jobs
                SET status      = CASE WHEN attempts >= :max_attempts THEN 'failed' ELSE 'pending' END,
                    error       = :error,
                    finished_at = CASE WHEN attempts >= :max_attempts THEN now() ELSE NULL END
                WHERE id = :id
            """),
            {"id": job_id, "error": error[:2000], "max_attempts": _MAX_ATTEMPTS},
        )
        db.commit()


def _process_telegram_job(payload: list[dict]) -> None:
    from backend.services.telegram_client import bot_client
    from backend.services.telegram_processor import MessageProcessor
    MessageProcessor(bot_client).process(payload)


def _process_whatsapp_job(payload: list[dict]) -> None:
    from backend.services.whatsapp_client import WhatsAppClient
    from backend.services.whatsapp_processor import MessageProcessor
    MessageProcessor(WhatsAppClient()).process(payload)


def _process_job(job: dict) -> None:
    canal = job["canal"]
    raw_payload = job["payload"]
    payload = raw_payload if isinstance(raw_payload, list) else json.loads(raw_payload)

    logger.info("Processando job id=%s canal=%s chat_id=%s", job["id"], canal, job["chat_id"])

    if canal == "telegram":
        _process_telegram_job(payload)
    elif canal == "whatsapp":
        _process_whatsapp_job(payload)
    else:
        raise ValueError(f"Canal desconhecido: {canal}")


def _run_single_job(job: dict) -> None:
    """Processa um único job e atualiza seu status. Executado dentro do pool de threads."""
    job_id = job["id"]
    t0 = time.monotonic()
    try:
        _process_job(job)
        elapsed = time.monotonic() - t0
        _mark_done(job_id)
        logger.info("Job %s concluído em %.1fs.", job_id, elapsed)
        if elapsed > 30:
            logger.warning("[TIMING] Job %s demorou %.1fs — acima do esperado.", job_id, elapsed)
    except Exception as exc:
        elapsed = time.monotonic() - t0
        logger.error("Erro ao processar job %s após %.1fs: %s", job_id, elapsed, exc, exc_info=True)
        _mark_error(job_id, str(exc))


def enqueue(canal: str, chat_id: str, payload: list[dict]) -> None:
    """Enqueue a new agent job. Called from webhook handlers."""
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO agent_jobs (canal, chat_id, payload, env) "
                "VALUES (:canal, :chat_id, CAST(:payload AS jsonb), :env)"
            ),
            {"canal": canal, "chat_id": chat_id, "payload": json.dumps(payload), "env": _ENV},
        )
        db.commit()


def run_worker() -> None:
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

    logger.info(
        "Agent worker iniciado. poll_interval=%.1fs max_attempts=%d concurrency=%d env=%s",
        _POLL_INTERVAL_SECONDS, _MAX_ATTEMPTS, _WORKER_CONCURRENCY, _ENV,
    )
    _reclaim_stale_processing_jobs()

    active: set[Future] = set()
    lock = threading.Lock()

    def _on_done(f: Future) -> None:
        with lock:
            active.discard(f)

    with ThreadPoolExecutor(
        max_workers=_WORKER_CONCURRENCY, thread_name_prefix="agent-job"
    ) as executor:
        while _running:
            try:
                with lock:
                    n_active = len(active)

                # Não reivindica novos jobs se todos os slots estão ocupados
                if n_active >= _WORKER_CONCURRENCY:
                    time.sleep(0.1)
                    continue

                with SessionLocal() as db:
                    job = _claim_job(db)

                if job is None:
                    time.sleep(_POLL_INTERVAL_SECONDS)
                    continue

                fut = executor.submit(_run_single_job, job)
                with lock:
                    active.add(fut)
                fut.add_done_callback(_on_done)

            except Exception as exc:
                logger.error("Erro inesperado no loop do worker: %s", exc, exc_info=True)
                time.sleep(_POLL_INTERVAL_SECONDS * 5)

    logger.info("Worker encerrado.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run_worker()
