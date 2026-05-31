-- Migration 043: Ampliar dimensão do embedding de conversas de 768 para 3072
-- pgvector não indexa vetores com mais de 2000 dims (IVFFlat nem HNSW).
-- A tabela conversas é pequena; sequential scan é aceitável para busca por memória.

DROP INDEX IF EXISTS idx_conversas_embedding;

ALTER TABLE conversas
    ALTER COLUMN embedding TYPE VECTOR(3072) USING NULL;
