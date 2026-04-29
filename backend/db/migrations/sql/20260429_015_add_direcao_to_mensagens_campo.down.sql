-- Rollback: Remove direcao field from mensagens_campo
-- Date: 2026-04-29
-- Description: Rollback of migration to add message direction (user/agent) tracking

-- Drop indexes
DROP INDEX IF EXISTS idx_mensagens_campo_chat_direcao;
DROP INDEX IF EXISTS idx_mensagens_campo_direcao;

-- Remove direcao column
ALTER TABLE mensagens_campo
DROP COLUMN IF EXISTS direcao;

-- Drop ENUM type
DROP TYPE IF EXISTS direcao_mensagem;
