-- Remover índice da tabela de imagens dos registros
DROP INDEX IF EXISTS idx_registro_imagens_registro;

-- Remover tabela de imagens vinculadas aos registros
DROP TABLE IF EXISTS registro_imagens;
