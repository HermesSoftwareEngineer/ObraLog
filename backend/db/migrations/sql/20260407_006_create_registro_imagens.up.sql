-- Criar tabela de imagens vinculadas aos registros
CREATE TABLE registro_imagens (
  id SERIAL PRIMARY KEY,
  registro_id INT NOT NULL REFERENCES registros(id) ON DELETE CASCADE,
  storage_path VARCHAR,
  external_url VARCHAR,
  mime_type VARCHAR,
  file_size INT,
  origem VARCHAR NOT NULL DEFAULT 'api',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Índice para listagem rápida por registro
CREATE INDEX idx_registro_imagens_registro ON registro_imagens(registro_id);
