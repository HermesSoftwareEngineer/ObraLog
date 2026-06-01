DROP INDEX IF EXISTS idx_agent_jobs_env_status;
ALTER TABLE agent_jobs DROP COLUMN IF EXISTS env;
