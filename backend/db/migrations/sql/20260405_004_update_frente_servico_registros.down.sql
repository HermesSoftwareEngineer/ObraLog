-- Reverter mudanças em registros
ALTER TABLE registros
ADD COLUMN hora_registro TIME NOT NULL DEFAULT CURRENT_TIME;

ALTER TABLE registros
DROP COLUMN observacao;

ALTER TABLE registros
ALTER COLUMN data SET NOT NULL;

ALTER TABLE registros
ALTER COLUMN usuario_registrador_id DROP NOT NULL;

ALTER TABLE registros
ALTER COLUMN frente_servico_id DROP NOT NULL;

-- Reverter mudanças em frentes_servico
ALTER TABLE frentes_servico
DROP COLUMN observacao;

ALTER TABLE frentes_servico
ALTER COLUMN encarregado_responsavel SET NOT NULL;
