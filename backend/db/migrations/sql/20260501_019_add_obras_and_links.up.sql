-- Migration: Add obras table and link registros/alerts
-- Date: 2026-05-01
-- Number: 019

BEGIN;

CREATE TABLE IF NOT EXISTS obras (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    codigo VARCHAR(80),
    descricao TEXT,
    ativo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    tenant_id INT NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
    CONSTRAINT uq_obras_codigo_tenant UNIQUE (tenant_id, codigo)
);

ALTER TABLE registros
    ADD COLUMN IF NOT EXISTS obra_id INT REFERENCES obras(id) ON DELETE SET NULL;

ALTER TABLE alerts
    ADD COLUMN IF NOT EXISTS obra_id INT REFERENCES obras(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_obras_tenant_id ON obras(tenant_id);
CREATE INDEX IF NOT EXISTS idx_registros_obra_id ON registros(obra_id);
CREATE INDEX IF NOT EXISTS idx_alerts_obra_id ON alerts(obra_id);

COMMIT;
