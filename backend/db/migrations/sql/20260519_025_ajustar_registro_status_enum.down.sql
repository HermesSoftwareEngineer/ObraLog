-- Migration 025 DOWN: Reverter registro_status para valores originais
-- Date: 2026-05-19

BEGIN;

-- 1. Remover nova constraint
ALTER TABLE registros DROP CONSTRAINT IF EXISTS ck_registros_aprovado_campos_basicos;
ALTER TABLE registros DROP CONSTRAINT IF EXISTS ck_registros_consolidado_campos_basicos;

-- 2. Converter coluna para TEXT
ALTER TABLE registros ALTER COLUMN status DROP DEFAULT;
ALTER TABLE registros ALTER COLUMN status TYPE TEXT USING status::TEXT;

-- 3. Reverter dados
UPDATE registros SET status = 'consolidado' WHERE status = 'aprovado';
UPDATE registros SET status = 'descartado'  WHERE status = 'rejeitado';
-- pendente permanece pendente

-- 4. Recriar tipo original
DROP TYPE IF EXISTS registro_status;
CREATE TYPE registro_status AS ENUM ('pendente', 'consolidado', 'revisado', 'ativo', 'descartado');

-- 5. Converter coluna de volta
ALTER TABLE registros
    ALTER COLUMN status TYPE registro_status USING status::registro_status;
ALTER TABLE registros ALTER COLUMN status SET NOT NULL;
ALTER TABLE registros ALTER COLUMN status SET DEFAULT 'pendente'::registro_status;

-- 6. Restaurar constraint original
ALTER TABLE registros
ADD CONSTRAINT ck_registros_consolidado_campos_basicos
CHECK (
    status <> 'consolidado'
    OR (
        data IS NOT NULL
        AND frente_servico_id IS NOT NULL
        AND usuario_registrador_id IS NOT NULL
        AND tempo_manha IS NOT NULL
        AND tempo_tarde IS NOT NULL
        AND (
            (
                COALESCE(LOWER(metadata_json->>'tipo'), 'estaca') IN ('texto', 'text')
                AND estaca IS NOT NULL
            )
            OR
            (
                COALESCE(LOWER(metadata_json->>'tipo'), 'estaca') NOT IN ('texto', 'text')
                AND estaca_inicial IS NOT NULL
                AND estaca_final IS NOT NULL
                AND resultado IS NOT NULL
            )
        )
    )
) NOT VALID;

COMMIT;
