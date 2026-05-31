-- Migration 044: Acesso multi-tenant para administradores
-- Admins podem ser associados a múltiplos tenants.
-- eh_padrao marca o tenant ativo padrão (usado pelo agente Telegram e no login).

CREATE TABLE usuario_tenants (
    id         SERIAL  PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id)  ON DELETE CASCADE,
    tenant_id  INTEGER NOT NULL REFERENCES tenants(id)   ON DELETE CASCADE,
    eh_padrao  BOOLEAN NOT NULL DEFAULT false,
    ativo      BOOLEAN NOT NULL DEFAULT true,
    CONSTRAINT uq_usuario_tenants_usuario_tenant UNIQUE (usuario_id, tenant_id)
);

CREATE INDEX idx_usuario_tenants_usuario_id ON usuario_tenants(usuario_id);
CREATE INDEX idx_usuario_tenants_tenant_id  ON usuario_tenants(tenant_id);

-- Backfill: admins existentes ganham acesso ao seu tenant atual como padrão
INSERT INTO usuario_tenants (usuario_id, tenant_id, eh_padrao, ativo)
SELECT id, tenant_id, true, true
FROM usuarios
WHERE nivel_acesso = 'administrador'
ON CONFLICT DO NOTHING;
