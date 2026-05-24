-- Migration 033: Create diario_versoes table
-- Date: 2026-05-19

CREATE TABLE IF NOT EXISTS diario_versoes (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  diario_id    UUID NOT NULL REFERENCES diarios(id)  ON DELETE CASCADE,
  tenant_id    INT  NOT NULL REFERENCES tenants(id)  ON DELETE RESTRICT,
  versao       INT  NOT NULL,
  storage_path VARCHAR NOT NULL,
  storage_url  VARCHAR,
  gerado_por   INT REFERENCES usuarios(id) ON DELETE SET NULL,
  gerado_em    TIMESTAMPTZ NOT NULL DEFAULT now(),
  motivo_regeracao TEXT,
  registros_ids    JSONB NOT NULL DEFAULT '[]',

  UNIQUE(diario_id, versao)
);

CREATE INDEX IF NOT EXISTS idx_diario_versoes_diario ON diario_versoes(diario_id);
