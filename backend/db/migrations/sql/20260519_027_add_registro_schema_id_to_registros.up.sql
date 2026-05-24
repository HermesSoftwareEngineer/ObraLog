-- Migration 027: Add registro_schema_id to registros
-- Date: 2026-05-19

ALTER TABLE registros
    ADD COLUMN IF NOT EXISTS registro_schema_id INT REFERENCES registro_schemas(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_registros_registro_schema ON registros (registro_schema_id);
