-- Migration 023: Create usuario_obras table
-- Date: 2026-05-19

CREATE TABLE IF NOT EXISTS usuario_obras (
    id         SERIAL PRIMARY KEY,
    usuario_id INT     NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    obra_id    INT     NOT NULL REFERENCES obras(id)    ON DELETE CASCADE,
    ativo      BOOLEAN NOT NULL DEFAULT true,
    eh_padrao  BOOLEAN NOT NULL DEFAULT false,
    tenant_id  INT     NOT NULL REFERENCES tenants(id)  ON DELETE RESTRICT,
    UNIQUE (usuario_id, obra_id)
);

CREATE INDEX IF NOT EXISTS idx_usuario_obras_usuario ON usuario_obras (usuario_id);
CREATE INDEX IF NOT EXISTS idx_usuario_obras_obra    ON usuario_obras (obra_id);
CREATE INDEX IF NOT EXISTS idx_usuario_obras_tenant  ON usuario_obras (tenant_id);
