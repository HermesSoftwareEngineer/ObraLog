-- Rollback: Multi-tenant support
-- Date: 2026-05-01
-- Number: 016
-- Description:
--   Reverses migration 016.  Order of operations:
--     1. Drop composite and tenant_id indexes.
--     2. Restore original global unique constraints.
--     3. Drop per-tenant unique constraints.
--     4. Drop tenant_id columns from domain tables.
--     5. Drop tenants table.
--
-- WARNING: This rollback is only safe if no new tenant rows (other than the
-- default) have been created and no application code relies on tenant_id.

BEGIN;

-- =============================================================
-- STEP 1: Drop composite indexes added in UP
-- =============================================================

DROP INDEX IF EXISTS idx_mensagens_campo_tenant_chat;
DROP INDEX IF EXISTS idx_alerts_tenant_status;
DROP INDEX IF EXISTS idx_registros_tenant_frente;
DROP INDEX IF EXISTS idx_registros_tenant_data;

DROP INDEX IF EXISTS idx_telegram_link_codes_tenant_id;
DROP INDEX IF EXISTS idx_alert_type_aliases_tenant_id;
DROP INDEX IF EXISTS idx_alert_reads_tenant_id;
DROP INDEX IF EXISTS idx_alerts_tenant_id;
DROP INDEX IF EXISTS idx_mensagens_campo_tenant_id;
DROP INDEX IF EXISTS idx_registro_imagens_tenant_id;
DROP INDEX IF EXISTS idx_registros_tenant_id;
DROP INDEX IF EXISTS idx_frentes_servico_tenant_id;
DROP INDEX IF EXISTS idx_usuarios_tenant_id;

-- =============================================================
-- STEP 2: Restore original global unique constraints
-- =============================================================

-- usuarios.email: restore global unique
ALTER TABLE usuarios
    DROP CONSTRAINT IF EXISTS uq_usuarios_email_tenant;

ALTER TABLE usuarios
    ADD CONSTRAINT usuarios_email_key UNIQUE (email);

-- alerts.code: restore global unique
ALTER TABLE alerts
    DROP CONSTRAINT IF EXISTS uq_alerts_code_tenant;

ALTER TABLE alerts
    ADD CONSTRAINT alerts_code_key UNIQUE (code);

-- alert_type_aliases: restore global uniques
ALTER TABLE alert_type_aliases
    DROP CONSTRAINT IF EXISTS uq_alert_type_aliases_alias_tenant;

ALTER TABLE alert_type_aliases
    DROP CONSTRAINT IF EXISTS uq_alert_type_aliases_normalized_alias_tenant;

ALTER TABLE alert_type_aliases
    ADD CONSTRAINT alert_type_aliases_alias_key UNIQUE (alias);

ALTER TABLE alert_type_aliases
    ADD CONSTRAINT alert_type_aliases_normalized_alias_key UNIQUE (normalized_alias);

CREATE UNIQUE INDEX idx_alert_type_aliases_alias_unique
    ON alert_type_aliases(alias);

CREATE UNIQUE INDEX idx_alert_type_aliases_normalized_alias_unique
    ON alert_type_aliases(normalized_alias);

-- =============================================================
-- STEP 3: Drop tenant_id FK columns from domain tables
-- =============================================================

ALTER TABLE telegram_link_codes DROP COLUMN IF EXISTS tenant_id;
ALTER TABLE alert_type_aliases  DROP COLUMN IF EXISTS tenant_id;
ALTER TABLE alert_reads         DROP COLUMN IF EXISTS tenant_id;
ALTER TABLE alerts              DROP COLUMN IF EXISTS tenant_id;
ALTER TABLE mensagens_campo     DROP COLUMN IF EXISTS tenant_id;
ALTER TABLE registro_imagens    DROP COLUMN IF EXISTS tenant_id;
ALTER TABLE registros           DROP COLUMN IF EXISTS tenant_id;
ALTER TABLE frentes_servico     DROP COLUMN IF EXISTS tenant_id;
ALTER TABLE usuarios            DROP COLUMN IF EXISTS tenant_id;

-- =============================================================
-- STEP 4: Drop tenants table
-- =============================================================

DROP TABLE IF EXISTS tenants;

COMMIT;
