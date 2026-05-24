-- Migration 037: Add ambiente to conversas
-- Date: 2026-05-23
-- 'prod' é o padrão. Conversas existentes assumem prod.

ALTER TABLE conversas
  ADD COLUMN ambiente VARCHAR(10) NOT NULL DEFAULT 'prod';

CREATE INDEX IF NOT EXISTS idx_conversas_ambiente ON conversas(ambiente);
