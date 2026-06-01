-- Migration 046: Isola jobs por ambiente (dev/prod) para evitar que worker de dev processe jobs de prod
ALTER TABLE agent_jobs ADD COLUMN IF NOT EXISTS env VARCHAR(50) NOT NULL DEFAULT 'prod';

CREATE INDEX IF NOT EXISTS idx_agent_jobs_env_status ON agent_jobs (env, status, created_at);
