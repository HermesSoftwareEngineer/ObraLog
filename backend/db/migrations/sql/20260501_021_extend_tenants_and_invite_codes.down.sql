-- =============================================================
-- Migration 021 DOWN: Remove invite codes table + tenant company fields
-- =============================================================

DROP TABLE IF EXISTS user_invite_codes;

ALTER TABLE tenants
    DROP COLUMN IF EXISTS cnpj,
    DROP COLUMN IF EXISTS razao_social,
    DROP COLUMN IF EXISTS nome_fantasia,
    DROP COLUMN IF EXISTS logradouro,
    DROP COLUMN IF EXISTS numero,
    DROP COLUMN IF EXISTS complemento,
    DROP COLUMN IF EXISTS cep,
    DROP COLUMN IF EXISTS cidade,
    DROP COLUMN IF EXISTS estado,
    DROP COLUMN IF EXISTS telefone_comercial,
    DROP COLUMN IF EXISTS email_comercial;
