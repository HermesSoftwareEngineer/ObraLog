DROP INDEX IF EXISTS idx_registros_status;

ALTER TABLE registros DROP CONSTRAINT IF EXISTS ck_registros_consolidado_campos_basicos;

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
) NOT VALID;

UPDATE registros
SET data = CURRENT_DATE
WHERE data IS NULL;

UPDATE registros
SET frente_servico_id = (
    SELECT id FROM frentes_servico ORDER BY id ASC LIMIT 1
)
WHERE frente_servico_id IS NULL;

UPDATE registros
SET usuario_registrador_id = (
    SELECT id FROM usuarios ORDER BY id ASC LIMIT 1
)
WHERE usuario_registrador_id IS NULL;

UPDATE registros
SET estaca_inicial = 0
WHERE estaca_inicial IS NULL;

UPDATE registros
SET estaca_final = 0
WHERE estaca_final IS NULL;

UPDATE registros
SET resultado = COALESCE(estaca_final, 0) - COALESCE(estaca_inicial, 0)
WHERE resultado IS NULL;

UPDATE registros
SET tempo_manha = 'nublado'
WHERE tempo_manha IS NULL;

UPDATE registros
SET tempo_tarde = 'nublado'
WHERE tempo_tarde IS NULL;

ALTER TABLE registros ALTER COLUMN data SET NOT NULL;
ALTER TABLE registros ALTER COLUMN frente_servico_id SET NOT NULL;
ALTER TABLE registros ALTER COLUMN usuario_registrador_id SET NOT NULL;
ALTER TABLE registros ALTER COLUMN estaca_inicial SET NOT NULL;
ALTER TABLE registros ALTER COLUMN estaca_final SET NOT NULL;
ALTER TABLE registros ALTER COLUMN resultado SET NOT NULL;
ALTER TABLE registros ALTER COLUMN tempo_manha SET NOT NULL;
ALTER TABLE registros ALTER COLUMN tempo_tarde SET NOT NULL;

ALTER TABLE registros DROP COLUMN IF EXISTS status;
DROP TYPE IF EXISTS registro_status;
