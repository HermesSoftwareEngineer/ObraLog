"""Worker interno da fila agent_jobs — poll sequencial com SELECT FOR UPDATE SKIP LOCKED."""
from __future__ import annotations

import json
import logging
import threading
import time

from sqlalchemy import text

logger = logging.getLogger("obralog.jobs.agent_worker")

_worker_lock = threading.Lock()
_worker_started = False


def enqueue_job(canal: str, chat_id: str, payload: dict, env: str) -> int:
    from backend.db.session import SessionLocal

    with SessionLocal() as db:
        row = db.execute(
            text(
                "INSERT INTO agent_jobs (canal, chat_id, payload, status, env, created_at) "
                "VALUES (:canal, :chat_id, :payload, 'pending', :env, now()) "
                "RETURNING id"
            ),
            {
                "canal": canal,
                "chat_id": chat_id,
                "payload": json.dumps(payload, ensure_ascii=False),
                "env": env,
            },
        ).fetchone()
        db.commit()

    job_id = row[0]
    print(f"[WORKER] job enfileirado id={job_id} canal={canal} chat_id={chat_id} env={env}", flush=True)
    return job_id


def _process_one_job(job_id: int, job_payload: dict) -> None:
    from backend.db.session import SessionLocal
    from backend.services.telegram_client import bot_client
    from backend.services.telegram_processor import MessageProcessor

    print(f"[WORKER] iniciando job id={job_id}", flush=True)

    try:
        updates = job_payload if isinstance(job_payload, list) else job_payload.get("updates", [])
        MessageProcessor(bot_client).process(updates)

        with SessionLocal() as db:
            db.execute(
                text("UPDATE agent_jobs SET status='done', finished_at=now() WHERE id=:id"),
                {"id": job_id},
            )
            db.commit()
        print(f"[WORKER] job id={job_id} concluído", flush=True)

    except Exception as exc:
        logger.error("[WORKER] job %s falhou: %s", job_id, exc, exc_info=True)
        print(f"[WORKER] job id={job_id} falhou: {exc}", flush=True)
        with SessionLocal() as db:
            db.execute(
                text(
                    "UPDATE agent_jobs SET status='failed', error=:error, finished_at=now() WHERE id=:id"
                ),
                {"id": job_id, "error": str(exc)[:2000]},
            )
            db.commit()


def _poll_loop() -> None:
    from backend.core.config import get_ambiente
    from backend.db.session import SessionLocal

    env = get_ambiente()
    print(f"[WORKER] poll loop iniciado env={env}", flush=True)

    while True:
        try:
            job_id: int | None = None
            job_payload: dict | None = None

            with SessionLocal() as db:
                row = db.execute(
                    text(
                        """
                        SELECT id, payload FROM agent_jobs
                        WHERE status IN ('pending', 'failed')
                          AND env = :env
                          AND attempts < 3
                        ORDER BY created_at
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                        """
                    ),
                    {"env": env},
                ).fetchone()

                if row is not None:
                    job_id = row[0]
                    job_payload = row[1]  # psycopg3 desserializa jsonb → dict
                    db.execute(
                        text(
                            "UPDATE agent_jobs "
                            "SET status='running', started_at=now(), attempts=attempts+1 "
                            "WHERE id=:id"
                        ),
                        {"id": job_id},
                    )
                    db.commit()
                else:
                    db.rollback()

            if job_id is not None:
                _process_one_job(job_id, job_payload)
            else:
                time.sleep(2)

        except Exception as exc:
            logger.error("[WORKER] erro inesperado no poll loop: %s", exc, exc_info=True)
            print(f"[WORKER] erro inesperado no poll loop: {exc}", flush=True)
            time.sleep(5)


def start_worker_thread() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            print("[WORKER] thread já está ativa, ignorando.", flush=True)
            return
        _worker_started = True

    t = threading.Thread(target=_poll_loop, name="agent-worker", daemon=True)
    t.start()
    print("[WORKER] thread iniciada", flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=__import__("sys").stdout)
    start_worker_thread()
    # Mantém processo vivo para execução standalone em dev
    while True:
        time.sleep(60)
