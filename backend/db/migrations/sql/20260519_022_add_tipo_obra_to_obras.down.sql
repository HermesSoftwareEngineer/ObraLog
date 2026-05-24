-- Migration 022 DOWN

ALTER TABLE obras DROP COLUMN IF EXISTS tipo_obra;
