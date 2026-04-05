DROP INDEX IF EXISTS idx_usuarios_telefone_unique;
ALTER TABLE usuarios DROP COLUMN IF EXISTS telefone;
