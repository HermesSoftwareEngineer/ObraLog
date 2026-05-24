BEGIN;

ALTER TABLE registro_schemas
    ADD CONSTRAINT uq_registro_schemas_tenant_tipo
    UNIQUE (tenant_id, tipo_obra);

COMMIT;
