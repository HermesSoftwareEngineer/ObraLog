CREATE TABLE IF NOT EXISTS alert_type_aliases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  alias VARCHAR(120) NOT NULL UNIQUE,
  normalized_alias VARCHAR(120) NOT NULL UNIQUE,
  canonical_type alert_type NOT NULL,
  descricao TEXT,
  ativo BOOLEAN NOT NULL DEFAULT true,
  created_by INT REFERENCES usuarios(id) ON DELETE SET NULL,
  updated_by INT REFERENCES usuarios(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_type_aliases_alias_unique
  ON alert_type_aliases(alias);

CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_type_aliases_normalized_alias_unique
  ON alert_type_aliases(normalized_alias);

CREATE INDEX IF NOT EXISTS idx_alert_type_aliases_canonical_type
  ON alert_type_aliases(canonical_type);

CREATE INDEX IF NOT EXISTS idx_alert_type_aliases_ativo
  ON alert_type_aliases(ativo);
