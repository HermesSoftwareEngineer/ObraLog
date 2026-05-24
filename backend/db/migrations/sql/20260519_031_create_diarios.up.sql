-- Migration 031: Create diarios table
-- Date: 2026-05-19

DO $$ BEGIN
  CREATE TYPE diario_tipo AS ENUM ('diario', 'semanal', 'mensal');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE diario_status AS ENUM ('rascunho', 'finalizado');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS diarios (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  obra_id       INT NOT NULL REFERENCES obras(id) ON DELETE RESTRICT,
  tenant_id     INT NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
  tipo          diario_tipo   NOT NULL DEFAULT 'diario',
  status        diario_status NOT NULL DEFAULT 'rascunho',

  data_inicio DATE NOT NULL,
  data_fim    DATE NOT NULL,

  versao_atual    INT NOT NULL DEFAULT 1,
  gerado_por      INT REFERENCES usuarios(id) ON DELETE SET NULL,
  gerado_em       TIMESTAMPTZ,
  finalizado_por  INT REFERENCES usuarios(id) ON DELETE SET NULL,
  finalizado_em   TIMESTAMPTZ,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT diarios_unique_periodo UNIQUE (obra_id, tipo, data_inicio, data_fim)
);

CREATE INDEX IF NOT EXISTS idx_diarios_obra_tipo ON diarios(obra_id, tipo);
CREATE INDEX IF NOT EXISTS idx_diarios_tenant    ON diarios(tenant_id);
CREATE INDEX IF NOT EXISTS idx_diarios_status    ON diarios(status);
