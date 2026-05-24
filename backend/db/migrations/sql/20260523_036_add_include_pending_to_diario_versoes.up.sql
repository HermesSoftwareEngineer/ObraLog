-- Migration 036: Add include_pending to diario_versoes
-- Date: 2026-05-23
-- Registros existentes assumem FALSE (apenas aprovados), pois não há como saber
-- retroativamente o critério usado na geração original.

ALTER TABLE diario_versoes
  ADD COLUMN include_pending BOOLEAN NOT NULL DEFAULT FALSE;

-- Explicita que versões já existentes foram geradas apenas com registros aprovados.
UPDATE diario_versoes SET include_pending = FALSE WHERE include_pending IS DISTINCT FROM FALSE;
