-- Migration 024: Add obra_id to frentes_servico
-- Date: 2026-05-19

ALTER TABLE frentes_servico ADD COLUMN IF NOT EXISTS obra_id INT REFERENCES obras(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_frentes_servico_obra ON frentes_servico (obra_id);
