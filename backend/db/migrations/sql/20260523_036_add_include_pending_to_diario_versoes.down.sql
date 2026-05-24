-- Migration 036: Rollback include_pending from diario_versoes
-- Date: 2026-05-23

ALTER TABLE diario_versoes
  DROP COLUMN include_pending;
