BEGIN;

DROP INDEX IF EXISTS idx_frentes_servico_registro_schema_id;

ALTER TABLE frentes_servico
    DROP COLUMN IF EXISTS registro_schema_id;

-- Restaura a constraint de unicidade (tenant, tipo_obra_id).
-- ATENÇÃO: só será possível re-aplicar se não existirem schemas duplicados
-- para o mesmo tipo_obra_id no banco. Limpe duplicatas antes se necessário.
ALTER TABLE registro_schemas
    ADD CONSTRAINT uq_registro_schemas_tenant_tipo_id
    UNIQUE (tenant_id, tipo_obra_id);

COMMIT;
