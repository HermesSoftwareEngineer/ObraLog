-- Migration 048: Create conversa_resumos for semantic conversation history search
-- Stores enriched documents (summary + key entities) with pgvector embeddings.
-- Dimension 768 matches Google text-embedding-004 and supports HNSW indexing.

CREATE TABLE IF NOT EXISTS conversa_resumos (
    id                    BIGSERIAL PRIMARY KEY,
    conversa_id           BIGINT    NOT NULL REFERENCES conversas(id) ON DELETE CASCADE,
    resumo                TEXT      NOT NULL,
    documento_enriquecido TEXT      NOT NULL,
    embedding             VECTOR(768),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversa_resumos_conversa_id
    ON conversa_resumos(conversa_id);

CREATE INDEX IF NOT EXISTS idx_conversa_resumos_embedding
    ON conversa_resumos USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE embedding IS NOT NULL;
