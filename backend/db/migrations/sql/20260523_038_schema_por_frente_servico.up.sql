BEGIN;

-- Remove constraint que limitava a um schema por tipo de obra por tenant.
-- A partir de agora, uma obra pode ter múltiplos schemas (um por frente de serviço).
ALTER TABLE registro_schemas
    DROP CONSTRAINT IF EXISTS uq_registro_schemas_tenant_tipo_id;

-- Adiciona FK de frente_servico → registro_schema (nullable: frentes existentes
-- ficam sem schema até serem configuradas manualmente).
ALTER TABLE frentes_servico
    ADD COLUMN IF NOT EXISTS registro_schema_id INTEGER
    REFERENCES registro_schemas(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_frentes_servico_registro_schema_id
    ON frentes_servico (registro_schema_id);

COMMIT;
