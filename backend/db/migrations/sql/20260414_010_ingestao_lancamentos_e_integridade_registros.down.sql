DROP INDEX IF EXISTS idx_lancamento_midias_lancamento;
DROP INDEX IF EXISTS idx_lancamento_recursos_lancamento;
DROP INDEX IF EXISTS idx_lancamento_itens_lancamento;
DROP INDEX IF EXISTS idx_lancamentos_diario_status;
DROP INDEX IF EXISTS idx_lancamentos_diario_data;
DROP INDEX IF EXISTS idx_mensagens_campo_recebida_em;
DROP INDEX IF EXISTS idx_mensagens_campo_status;
DROP INDEX IF EXISTS uq_mensagens_campo_telegram_msg;

ALTER TABLE registros DROP CONSTRAINT IF EXISTS registros_source_message_id_fkey;
ALTER TABLE registros DROP COLUMN IF EXISTS source_message_id;
ALTER TABLE registros DROP COLUMN IF EXISTS raw_text;
ALTER TABLE registros DROP COLUMN IF EXISTS updated_at;

ALTER TABLE registros DROP CONSTRAINT IF EXISTS registros_usuario_registrador_id_fkey;
ALTER TABLE registros
ADD CONSTRAINT registros_usuario_registrador_id_fkey
FOREIGN KEY (usuario_registrador_id) REFERENCES usuarios(id) ON DELETE SET NULL;

ALTER TABLE registros DROP CONSTRAINT IF EXISTS ck_registros_required_fields;
ALTER TABLE registros
ADD CONSTRAINT ck_registros_required_fields
CHECK (
    data IS NOT NULL
    AND frente_servico_id IS NOT NULL
    AND usuario_registrador_id IS NOT NULL
    AND estaca_inicial IS NOT NULL
    AND estaca_final IS NOT NULL
    AND resultado IS NOT NULL
    AND tempo_manha IS NOT NULL
    AND tempo_tarde IS NOT NULL
    AND observacao IS NOT NULL
) NOT VALID;

ALTER TABLE registros ADD COLUMN IF NOT EXISTS pista lado_pista_enum;
UPDATE registros SET pista = lado_pista WHERE pista IS NULL AND lado_pista IS NOT NULL;

DROP TABLE IF EXISTS lancamento_midias;
DROP TABLE IF EXISTS lancamento_recursos;
DROP TABLE IF EXISTS lancamento_itens;
DROP TABLE IF EXISTS lancamentos_diario;
DROP TABLE IF EXISTS mensagens_campo;

DROP TYPE IF EXISTS recurso_categoria;
DROP TYPE IF EXISTS lancamento_tipo_item;
DROP TYPE IF EXISTS lancamento_status;
DROP TYPE IF EXISTS processamento_mensagem_status;
DROP TYPE IF EXISTS conteudo_mensagem_tipo;
DROP TYPE IF EXISTS canal_origem_mensagem;
