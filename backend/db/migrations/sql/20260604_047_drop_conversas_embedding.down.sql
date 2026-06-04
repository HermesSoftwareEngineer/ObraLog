-- Rollback 047: Recria coluna embedding (requer extensão pgvector)
ALTER TABLE conversas ADD COLUMN IF NOT EXISTS embedding VECTOR(3072);
