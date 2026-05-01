-- Migration: Multi-tenant support
-- Date: 2026-05-01
-- Number: 016
-- Description:
--   Introduce the `tenants` table and propagate tenant_id to every domain
--   table.  Strategy is safe for existing data:
--     1. Create tenants table.
--     2. Insert the "default" tenant (absorbs all legacy rows).
--     3. Add tenant_id as NULLABLE FK to each domain table.
--     4. Backfill every row with the default tenant id.
--     5. Set tenant_id NOT NULL.
--     6. Drop global uniques that must become per-tenant.
--     7. Add per-tenant unique constraints where semantically correct.
--     8. Create tenant_id indexes for query performance.
--
-- Rollback: see 20260501_016_multi_tenant.down.sql

BEGIN;

-- =============================================================
-- STEP 1: Create tenants table
-- =============================================================

CREATE TABLE tenants (
    id            SERIAL       PRIMARY KEY,
    nome          VARCHAR(200) NOT NULL,
    slug          VARCHAR(100) NOT NULL,
    tipo_negocio  VARCHAR(100),
    ativo         BOOLEAN      NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_tenants_slug UNIQUE (slug)
);

-- =============================================================
-- STEP 2: Default tenant (absorbs all legacy data)
-- =============================================================

INSERT INTO tenants (nome, slug, tipo_negocio, ativo)
VALUES ('Default', 'default', NULL, true);

-- =============================================================
-- STEP 3: Add tenant_id (nullable) to all domain tables
-- =============================================================

ALTER TABLE usuarios
    ADD COLUMN tenant_id INT REFERENCES tenants(id) ON DELETE RESTRICT;

ALTER TABLE frentes_servico
    ADD COLUMN tenant_id INT REFERENCES tenants(id) ON DELETE RESTRICT;

ALTER TABLE registros
    ADD COLUMN tenant_id INT REFERENCES tenants(id) ON DELETE RESTRICT;

ALTER TABLE registro_imagens
    ADD COLUMN tenant_id INT REFERENCES tenants(id) ON DELETE RESTRICT;

ALTER TABLE mensagens_campo
    ADD COLUMN tenant_id INT REFERENCES tenants(id) ON DELETE RESTRICT;

ALTER TABLE alerts
    ADD COLUMN tenant_id INT REFERENCES tenants(id) ON DELETE RESTRICT;

ALTER TABLE alert_reads
    ADD COLUMN tenant_id INT REFERENCES tenants(id) ON DELETE RESTRICT;

ALTER TABLE alert_type_aliases
    ADD COLUMN tenant_id INT REFERENCES tenants(id) ON DELETE RESTRICT;

ALTER TABLE telegram_link_codes
    ADD COLUMN tenant_id INT REFERENCES tenants(id) ON DELETE RESTRICT;

-- =============================================================
-- STEP 4: Backfill all rows with the default tenant
-- =============================================================

DO $$
DECLARE
    v_default_id INT;
BEGIN
    SELECT id INTO v_default_id FROM tenants WHERE slug = 'default';

    UPDATE usuarios            SET tenant_id = v_default_id WHERE tenant_id IS NULL;
    UPDATE frentes_servico     SET tenant_id = v_default_id WHERE tenant_id IS NULL;
    UPDATE registros           SET tenant_id = v_default_id WHERE tenant_id IS NULL;
    UPDATE registro_imagens    SET tenant_id = v_default_id WHERE tenant_id IS NULL;
    UPDATE mensagens_campo     SET tenant_id = v_default_id WHERE tenant_id IS NULL;
    UPDATE alerts              SET tenant_id = v_default_id WHERE tenant_id IS NULL;
    UPDATE alert_reads         SET tenant_id = v_default_id WHERE tenant_id IS NULL;
    UPDATE alert_type_aliases  SET tenant_id = v_default_id WHERE tenant_id IS NULL;
    UPDATE telegram_link_codes SET tenant_id = v_default_id WHERE tenant_id IS NULL;
END;
$$;

-- =============================================================
-- STEP 5: Enforce NOT NULL
-- =============================================================

ALTER TABLE usuarios            ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE frentes_servico     ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE registros           ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE registro_imagens    ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE mensagens_campo     ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE alerts              ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE alert_reads         ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE alert_type_aliases  ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE telegram_link_codes ALTER COLUMN tenant_id SET NOT NULL;

-- =============================================================
-- STEP 6: Adjust unique constraints
--
-- Rules applied:
--   * email        → unique per tenant (same person may work in two companies)
--   * alerts.code  → unique per tenant (each tenant has independent numbering)
--   * alias / normalized_alias → unique per tenant
--
-- Kept globally unique (intentional):
--   * telegram_chat_id / telegram_thread_id (one Telegram identity = one account)
--   * telefone (global phone numbers)
--   * telegram_link_codes.code (one-time tokens, must be globally unique)
--   * mensagens_campo.hash_idempotencia (Telegram message hash, global)
-- =============================================================

-- usuarios.email: drop global, replace with per-tenant
ALTER TABLE usuarios
    DROP CONSTRAINT IF EXISTS usuarios_email_key;

ALTER TABLE usuarios
    ADD CONSTRAINT uq_usuarios_email_tenant UNIQUE (tenant_id, email);

-- alerts.code: drop global, replace with per-tenant
ALTER TABLE alerts
    DROP CONSTRAINT IF EXISTS alerts_code_key;

ALTER TABLE alerts
    ADD CONSTRAINT uq_alerts_code_tenant UNIQUE (tenant_id, code);

-- alert_type_aliases: drop global uniques (column-level and index-level)
ALTER TABLE alert_type_aliases
    DROP CONSTRAINT IF EXISTS alert_type_aliases_alias_key;

ALTER TABLE alert_type_aliases
    DROP CONSTRAINT IF EXISTS alert_type_aliases_normalized_alias_key;

DROP INDEX IF EXISTS idx_alert_type_aliases_alias_unique;
DROP INDEX IF EXISTS idx_alert_type_aliases_normalized_alias_unique;

ALTER TABLE alert_type_aliases
    ADD CONSTRAINT uq_alert_type_aliases_alias_tenant
        UNIQUE (tenant_id, alias);

ALTER TABLE alert_type_aliases
    ADD CONSTRAINT uq_alert_type_aliases_normalized_alias_tenant
        UNIQUE (tenant_id, normalized_alias);

-- =============================================================
-- STEP 7: Indexes on tenant_id for frequent queries
-- =============================================================

CREATE INDEX idx_usuarios_tenant_id            ON usuarios(tenant_id);
CREATE INDEX idx_frentes_servico_tenant_id     ON frentes_servico(tenant_id);
CREATE INDEX idx_registros_tenant_id           ON registros(tenant_id);
CREATE INDEX idx_registro_imagens_tenant_id    ON registro_imagens(tenant_id);
CREATE INDEX idx_mensagens_campo_tenant_id     ON mensagens_campo(tenant_id);
CREATE INDEX idx_alerts_tenant_id              ON alerts(tenant_id);
CREATE INDEX idx_alert_reads_tenant_id         ON alert_reads(tenant_id);
CREATE INDEX idx_alert_type_aliases_tenant_id  ON alert_type_aliases(tenant_id);
CREATE INDEX idx_telegram_link_codes_tenant_id ON telegram_link_codes(tenant_id);

-- Composite indexes for the most common access patterns
CREATE INDEX idx_registros_tenant_data          ON registros(tenant_id, data);
CREATE INDEX idx_registros_tenant_frente        ON registros(tenant_id, frente_servico_id);
CREATE INDEX idx_alerts_tenant_status           ON alerts(tenant_id, status);
CREATE INDEX idx_mensagens_campo_tenant_chat    ON mensagens_campo(tenant_id, telegram_chat_id);

COMMIT;
