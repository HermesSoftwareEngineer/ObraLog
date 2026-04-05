-- Adicionar campo observacao em frentes_servico
ALTER TABLE frentes_servico
ADD COLUMN observacao TEXT;

-- Tornar encarregado_responsavel opcional em frentes_servico
ALTER TABLE frentes_servico
ALTER COLUMN encarregado_responsavel DROP NOT NULL;

-- Adicionar campo observacao em registros
ALTER TABLE registros
ADD COLUMN observacao TEXT;

-- Remover campo hora_registro em registros
ALTER TABLE registros
DROP COLUMN hora_registro;

-- Tornar campos opcionais em registros (todos exceto frente_servico_id que já é opcional)
ALTER TABLE registros
ALTER COLUMN data DROP NOT NULL;

ALTER TABLE registros
ALTER COLUMN usuario_registrador_id DROP NOT NULL;

-- Tornar frente_servico_id obrigatório em registros
ALTER TABLE registros
ALTER COLUMN frente_servico_id SET NOT NULL;
