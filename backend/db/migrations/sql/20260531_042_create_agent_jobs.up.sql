-- Migration 042: Fila assíncrona de jobs do agente (PostgreSQL SKIP LOCKED queue)
CREATE TABLE IF NOT EXISTS agent_jobs (
    id          BIGSERIAL    PRIMARY KEY,
    canal       VARCHAR(20)  NOT NULL,
    chat_id     VARCHAR      NOT NULL,
    payload     JSONB        NOT NULL,
    status      VARCHAR(20)  NOT NULL DEFAULT 'pending',
    error       TEXT,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    attempts    INT          NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_agent_jobs_status_created ON agent_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_jobs_chat_id        ON agent_jobs(chat_id);
