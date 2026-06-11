-- Migration 049 rollback: restaura campos removidos e desfaz alterações de schema

-- 1. Restaurar unique global de code
DROP INDEX IF EXISTS uq_alerts_code_tenant;
ALTER TABLE alerts ADD CONSTRAINT alerts_code_key UNIQUE (code);

-- 2. Remover tenant_id de alert_type_aliases
DROP INDEX IF EXISTS idx_alert_type_aliases_tenant_id;
ALTER TABLE alert_type_aliases DROP COLUMN IF EXISTS tenant_id;

-- 3. Remover tenant_id de alert_reads
DROP INDEX IF EXISTS idx_alert_reads_tenant_id;
ALTER TABLE alert_reads DROP COLUMN IF EXISTS tenant_id;

-- 4. Restaurar campo descricao em alert_type_aliases
ALTER TABLE alert_type_aliases ADD COLUMN IF NOT EXISTS descricao TEXT;

-- 5. Restaurar campos de leitura denormalizados em alerts
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS is_read   BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS read_at   TIMESTAMPTZ;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS read_by   INT REFERENCES usuarios(id);

-- 6. Restaurar campos mortos em alerts
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS priority_score SMALLINT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS notified_at    TIMESTAMPTZ;
