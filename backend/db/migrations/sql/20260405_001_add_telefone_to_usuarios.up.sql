ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telefone VARCHAR;
CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_telefone_unique ON usuarios(telefone) WHERE telefone IS NOT NULL;
