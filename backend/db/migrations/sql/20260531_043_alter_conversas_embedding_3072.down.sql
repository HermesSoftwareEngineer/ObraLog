ALTER TABLE conversas
    ALTER COLUMN embedding TYPE VECTOR(768) USING NULL;

CREATE INDEX IF NOT EXISTS idx_conversas_embedding
    ON conversas USING ivfflat (embedding vector_cosine_ops);
