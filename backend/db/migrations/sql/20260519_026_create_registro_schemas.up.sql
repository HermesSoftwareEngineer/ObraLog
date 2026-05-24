-- Migration 026: Create registro_schemas table
-- Date: 2026-05-19
--
-- Schema padrão de campos ativos por tipo de obra, por tenant.
-- É um template (1 por tenant+tipo), não por obra individual.
--
-- Estrutura de referência para campos_ativos:
-- {
--   "estaca_inicial": true, "estaca_final": true, "lado_pista": true,
--   "tempo_manha": true, "tempo_tarde": true, "resultado": true, "frente_servico": true
-- }
--
-- Estrutura de referência para campos_extras:
-- [{ "chave": "n_funcionarios", "label": "Nº de funcionários", "tipo": "number" }]

CREATE TABLE IF NOT EXISTS registro_schemas (
    id            SERIAL      PRIMARY KEY,
    tenant_id     INT         NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
    tipo_obra     VARCHAR(50) NOT NULL,  -- 'rodovia' | 'edificacao'
    nome          VARCHAR(200) NOT NULL,
    campos_ativos JSONB       NOT NULL DEFAULT '{}',
    campos_extras JSONB       NOT NULL DEFAULT '[]',
    ativo         BOOLEAN     NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, tipo_obra)
);

CREATE INDEX IF NOT EXISTS idx_registro_schemas_tenant ON registro_schemas (tenant_id);
CREATE INDEX IF NOT EXISTS idx_registro_schemas_tipo   ON registro_schemas (tipo_obra);
