-- Rollback: remove location_type from tenants
-- Date: 2026-05-01
-- Number: 018

BEGIN;

ALTER TABLE tenants
    DROP COLUMN IF EXISTS location_type;

COMMIT;