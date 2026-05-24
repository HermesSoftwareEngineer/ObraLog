BEGIN;

-- Remove o unique constraint legado sobre a coluna VARCHAR tipo_obra.
-- Esse constraint foi criado pela migration 026 com nome auto-gerado pelo Postgres
-- e nunca foi efetivamente removido (a 035 tentou dropar por um alias diferente).
-- Sem ele, uma obra pode ter múltiplos schemas de registro.
ALTER TABLE registro_schemas
    DROP CONSTRAINT IF EXISTS registro_schemas_tenant_id_tipo_obra_key;

-- Remove também qualquer variante nomeada manualmente, por segurança.
ALTER TABLE registro_schemas
    DROP CONSTRAINT IF EXISTS uq_registro_schemas_tenant_tipo;

COMMIT;
