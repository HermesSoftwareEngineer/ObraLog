BEGIN;

CREATE SEQUENCE IF NOT EXISTS tipos_obra_id_seq;

CREATE TABLE IF NOT EXISTS tipos_obra (
    id          INTEGER      NOT NULL DEFAULT nextval('tipos_obra_id_seq'),
    tenant_id   INTEGER      NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
    slug        VARCHAR(50)  NOT NULL,
    nome        VARCHAR(200) NOT NULL,
    descricao   TEXT,
    ativo       BOOLEAN      NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT tipos_obra_pkey PRIMARY KEY (id),
    CONSTRAINT tipos_obra_tenant_slug_unique UNIQUE (tenant_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_tipos_obra_tenant ON tipos_obra (tenant_id);
CREATE INDEX IF NOT EXISTS idx_tipos_obra_slug   ON tipos_obra (slug);

-- Seed: insere tipos padrão para cada tenant existente
INSERT INTO tipos_obra (tenant_id, slug, nome, descricao)
SELECT t.id, 'rodovia', 'Rodovia', 'Obras de construção e manutenção de rodovias'
FROM tenants t
WHERE NOT EXISTS (
    SELECT 1 FROM tipos_obra x WHERE x.tenant_id = t.id AND x.slug = 'rodovia'
);

INSERT INTO tipos_obra (tenant_id, slug, nome, descricao)
SELECT t.id, 'edificacao', 'Edificação', 'Obras de construção civil e edificações'
FROM tenants t
WHERE NOT EXISTS (
    SELECT 1 FROM tipos_obra x WHERE x.tenant_id = t.id AND x.slug = 'edificacao'
);

COMMIT;
