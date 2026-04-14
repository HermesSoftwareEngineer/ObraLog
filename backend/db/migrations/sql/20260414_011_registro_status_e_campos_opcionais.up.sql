DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'registro_status') THEN
        CREATE TYPE registro_status AS ENUM ('pendente', 'consolidado', 'revisado', 'ativo', 'descartado');
    END IF;
END $$;

ALTER TABLE registros ADD COLUMN IF NOT EXISTS status registro_status DEFAULT 'pendente';
UPDATE registros SET status = 'pendente' WHERE status IS NULL;
ALTER TABLE registros ALTER COLUMN status SET NOT NULL;

ALTER TABLE registros ALTER COLUMN data DROP NOT NULL;
ALTER TABLE registros ALTER COLUMN frente_servico_id DROP NOT NULL;
ALTER TABLE registros ALTER COLUMN usuario_registrador_id DROP NOT NULL;
ALTER TABLE registros ALTER COLUMN estaca_inicial DROP NOT NULL;
ALTER TABLE registros ALTER COLUMN estaca_final DROP NOT NULL;
ALTER TABLE registros ALTER COLUMN resultado DROP NOT NULL;
ALTER TABLE registros ALTER COLUMN tempo_manha DROP NOT NULL;
ALTER TABLE registros ALTER COLUMN tempo_tarde DROP NOT NULL;

ALTER TABLE registros DROP CONSTRAINT IF EXISTS ck_registros_required_fields;
ALTER TABLE registros DROP CONSTRAINT IF EXISTS ck_registros_consolidado_campos_basicos;

ALTER TABLE registros
ADD CONSTRAINT ck_registros_consolidado_campos_basicos
CHECK (
    status <> 'consolidado'
    OR (
        data IS NOT NULL
        AND frente_servico_id IS NOT NULL
        AND usuario_registrador_id IS NOT NULL
        AND estaca_inicial IS NOT NULL
        AND estaca_final IS NOT NULL
        AND resultado IS NOT NULL
        AND tempo_manha IS NOT NULL
        AND tempo_tarde IS NOT NULL
    )
) NOT VALID;

CREATE INDEX IF NOT EXISTS idx_registros_status ON registros(status);
