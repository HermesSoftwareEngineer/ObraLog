BEGIN;

ALTER TABLE registro_schemas
    DROP CONSTRAINT IF EXISTS uq_registro_schemas_tenant_tipo_id;

ALTER TABLE registro_schemas
    ADD CONSTRAINT uq_registro_schemas_tenant_tipo
    UNIQUE (tenant_id, tipo_obra);

ALTER TABLE registro_schemas DROP COLUMN IF EXISTS tipo_obra_id;
ALTER TABLE obras            DROP COLUMN IF EXISTS tipo_obra_id;

COMMIT;
