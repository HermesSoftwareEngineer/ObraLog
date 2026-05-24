-- Migration 030: Create conversas table (requires pgvector extension from migration 028)
-- Date: 2026-05-19
-- embedding dimension: 768 matches Google text-multilingual-embedding-002

CREATE TABLE IF NOT EXISTS conversas (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    usuario_id    INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    chat_id       VARCHAR NOT NULL,
    thread_id     VARCHAR NOT NULL,
    iniciada_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    encerrada_em  TIMESTAMPTZ,
    ultima_msg_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    resumo        TEXT,
    embedding     VECTOR(768)
);

CREATE INDEX IF NOT EXISTS idx_conversas_tenant_usuario ON conversas(tenant_id, usuario_id);
CREATE INDEX IF NOT EXISTS idx_conversas_aberta ON conversas(tenant_id, ultima_msg_em) WHERE encerrada_em IS NULL;
CREATE INDEX IF NOT EXISTS idx_conversas_embedding ON conversas USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50)
    WHERE embedding IS NOT NULL;
