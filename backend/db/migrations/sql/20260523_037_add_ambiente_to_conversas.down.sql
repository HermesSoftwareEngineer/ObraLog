-- Migration 037: Rollback ambiente from conversas
-- Date: 2026-05-23

DROP INDEX IF EXISTS idx_conversas_ambiente;

ALTER TABLE conversas
  DROP COLUMN ambiente;
