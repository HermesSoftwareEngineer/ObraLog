-- Rollback: Restore old consolidated check requiring estaca fields
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
        AND estaca_inicial IS NOT NULL
        AND estaca_final IS NOT NULL
        AND resultado IS NOT NULL
        AND tempo_manha IS NOT NULL
        AND tempo_tarde IS NOT NULL
    )
) NOT VALID;

COMMIT;
