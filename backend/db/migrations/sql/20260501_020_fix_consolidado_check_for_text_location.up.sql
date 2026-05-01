-- Migration: Fix consolidated check for text location registros
-- Date: 2026-05-01
-- Number: 020

BEGIN;

ALTER TABLE registros DROP CONSTRAINT IF EXISTS ck_registros_consolidado_campos_basicos;

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
