BEGIN;

-- obras: adiciona FK nullable para rollback seguro
ALTER TABLE obras
    ADD COLUMN IF NOT EXISTS tipo_obra_id INTEGER REFERENCES tipos_obra(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_obras_tipo_obra_id ON obras (tipo_obra_id);

-- Popula tipo_obra_id a partir do slug já existente em tipo_obra varchar
UPDATE obras o
SET tipo_obra_id = t.id
FROM tipos_obra t
WHERE t.tenant_id = o.tenant_id
  AND t.slug = o.tipo_obra
  AND o.tipo_obra IS NOT NULL
  AND o.tipo_obra_id IS NULL;

-- registro_schemas: adiciona FK nullable
ALTER TABLE registro_schemas
    ADD COLUMN IF NOT EXISTS tipo_obra_id INTEGER REFERENCES tipos_obra(id) ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS idx_registro_schemas_tipo_obra_id ON registro_schemas (tipo_obra_id);

-- Popula tipo_obra_id
UPDATE registro_schemas rs
SET tipo_obra_id = t.id
FROM tipos_obra t
WHERE t.tenant_id = rs.tenant_id
  AND t.slug = rs.tipo_obra
  AND rs.tipo_obra IS NOT NULL
  AND rs.tipo_obra_id IS NULL;

-- Troca unique constraint em registro_schemas para usar FK
ALTER TABLE registro_schemas
    DROP CONSTRAINT IF EXISTS uq_registro_schemas_tenant_tipo;

ALTER TABLE registro_schemas
    ADD CONSTRAINT uq_registro_schemas_tenant_tipo_id
    UNIQUE (tenant_id, tipo_obra_id);

COMMIT;
