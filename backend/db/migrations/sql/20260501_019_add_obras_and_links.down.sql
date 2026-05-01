-- Rollback: remove obra links and obras table
-- Date: 2026-05-01
-- Number: 019

BEGIN;

DROP INDEX IF EXISTS idx_alerts_obra_id;
DROP INDEX IF EXISTS idx_registros_obra_id;
DROP INDEX IF EXISTS idx_obras_tenant_id;

ALTER TABLE alerts DROP COLUMN IF EXISTS obra_id;
ALTER TABLE registros DROP COLUMN IF EXISTS obra_id;

DROP TABLE IF EXISTS obras;

COMMIT;
