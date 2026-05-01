-- =============================================================
-- Migration 021: Extend tenants with company fields + user_invite_codes
-- =============================================================

-- STEP 1: Add company fields to tenants
ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS cnpj               VARCHAR(18),
    ADD COLUMN IF NOT EXISTS razao_social       VARCHAR(200),
    ADD COLUMN IF NOT EXISTS nome_fantasia      VARCHAR(200),
    ADD COLUMN IF NOT EXISTS logradouro         VARCHAR(200),
    ADD COLUMN IF NOT EXISTS numero             VARCHAR(20),
    ADD COLUMN IF NOT EXISTS complemento        VARCHAR(100),
    ADD COLUMN IF NOT EXISTS cep                VARCHAR(9),
    ADD COLUMN IF NOT EXISTS cidade             VARCHAR(100),
    ADD COLUMN IF NOT EXISTS estado             VARCHAR(2),
    ADD COLUMN IF NOT EXISTS telefone_comercial VARCHAR(20),
    ADD COLUMN IF NOT EXISTS email_comercial    VARCHAR(200);

-- STEP 2: Create user_invite_codes table
CREATE TABLE IF NOT EXISTS user_invite_codes (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       INT         NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    criado_por      INT         NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
    email_destinatario VARCHAR(200),
    codigo          VARCHAR(32) NOT NULL UNIQUE,
    nivel_acesso    VARCHAR(50) NOT NULL DEFAULT 'encarregado',
    expira_em       TIMESTAMPTZ NOT NULL,
    usado_em        TIMESTAMPTZ,
    usado_por       INT         REFERENCES usuarios(id) ON DELETE SET NULL,
    ativo           BOOLEAN     NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_invite_codes_tenant  ON user_invite_codes (tenant_id);
CREATE INDEX IF NOT EXISTS idx_user_invite_codes_codigo  ON user_invite_codes (codigo);
