DROP INDEX IF EXISTS idx_lancamento_midias_lancamento;
DROP INDEX IF EXISTS idx_lancamento_recursos_lancamento;
DROP INDEX IF EXISTS idx_lancamento_itens_lancamento;
DROP INDEX IF EXISTS idx_lancamentos_diario_status;
DROP INDEX IF EXISTS idx_lancamentos_diario_data;

DROP TABLE IF EXISTS lancamento_midias;
DROP TABLE IF EXISTS lancamento_recursos;
DROP TABLE IF EXISTS lancamento_itens;
DROP TABLE IF EXISTS lancamentos_diario;

DROP TYPE IF EXISTS recurso_categoria;
DROP TYPE IF EXISTS lancamento_tipo_item;
DROP TYPE IF EXISTS lancamento_status;
