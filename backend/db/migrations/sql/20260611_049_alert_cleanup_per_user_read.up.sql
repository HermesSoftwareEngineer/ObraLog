-- Migration 049: Alert cleanup — leitura por usuário (Option B) + remoção de campos mortos
--
-- Remove campos que nunca foram usados (notified_at, priority_score) e os campos
-- de leitura denormalizados (is_read, read_at, read_by) que conflitavam com a
-- tabela alert_reads. A leitura passa a ser rastreada exclusivamente via alert_reads,
-- filtrada por usuário (uma linha por alerta × usuário).
--
-- Também remove 'descricao' de alert_type_aliases (nunca exibido) e garante
-- tenant_id em alert_reads e alert_type_aliases.

-- 1. Remover campos mortos de alerts
ALTER TABLE alerts DROP COLUMN IF EXISTS notified_at;
ALTER TABLE alerts DROP COLUMN IF EXISTS priority_score;
ALTER TABLE alerts DROP COLUMN IF EXISTS is_read;
ALTER TABLE alerts DROP COLUMN IF EXISTS read_at;
ALTER TABLE alerts DROP COLUMN IF EXISTS read_by;

-- 2. Remover campo morto de alert_type_aliases
ALTER TABLE alert_type_aliases DROP COLUMN IF EXISTS descricao;

-- 3. Garantir tenant_id em alert_reads (schema inicial não incluía a coluna)
ALTER TABLE alert_reads
    ADD COLUMN IF NOT EXISTS tenant_id INT REFERENCES tenants(id) ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS idx_alert_reads_tenant_id
    ON alert_reads(tenant_id);

-- 4. Garantir tenant_id em alert_type_aliases
ALTER TABLE alert_type_aliases
    ADD COLUMN IF NOT EXISTS tenant_id INT REFERENCES tenants(id) ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS idx_alert_type_aliases_tenant_id
    ON alert_type_aliases(tenant_id);

-- 5. Substituir unique global de code por unique por tenant
--    (o constraint antigo era UNIQUE(code) sem tenant_id)
ALTER TABLE alerts DROP CONSTRAINT IF EXISTS alerts_code_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_alerts_code_tenant
    ON alerts(tenant_id, code);
