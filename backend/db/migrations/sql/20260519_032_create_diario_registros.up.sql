-- Migration 032: Create diario_registros table
-- Date: 2026-05-19

CREATE TABLE IF NOT EXISTS diario_registros (
  id          SERIAL PRIMARY KEY,
  diario_id   UUID NOT NULL REFERENCES diarios(id)   ON DELETE CASCADE,
  registro_id INT  NOT NULL REFERENCES registros(id) ON DELETE RESTRICT,
  tenant_id   INT  NOT NULL REFERENCES tenants(id)   ON DELETE RESTRICT,
  UNIQUE(diario_id, registro_id)
);

CREATE INDEX IF NOT EXISTS idx_diario_registros_diario   ON diario_registros(diario_id);
CREATE INDEX IF NOT EXISTS idx_diario_registros_registro ON diario_registros(registro_id);
