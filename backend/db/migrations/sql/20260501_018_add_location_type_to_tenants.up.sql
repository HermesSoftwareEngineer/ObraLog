-- Migration: Add location_type to tenants
-- Date: 2026-05-01
-- Number: 018

BEGIN;

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS location_type VARCHAR(50);

ALTER TABLE tenants
    ALTER COLUMN location_type SET DEFAULT 'estaca';

UPDATE tenants
SET location_type = 'estaca'
WHERE location_type IS NULL;

ALTER TABLE tenants
    ALTER COLUMN location_type SET NOT NULL;

COMMIT;