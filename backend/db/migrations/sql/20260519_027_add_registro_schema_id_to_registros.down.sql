-- Migration 027 DOWN

ALTER TABLE registros DROP COLUMN IF EXISTS registro_schema_id;
