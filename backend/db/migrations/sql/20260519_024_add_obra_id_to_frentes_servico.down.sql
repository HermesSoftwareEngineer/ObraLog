-- Migration 024 DOWN

ALTER TABLE frentes_servico DROP COLUMN IF EXISTS obra_id;
