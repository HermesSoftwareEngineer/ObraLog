-- Migration 025: Ajustar registro_status para pendente | aprovado | rejeitado
-- Date: 2026-05-19
--
-- Mapeamento de valores existentes:
--   consolidado -> aprovado   (explicitamente solicitado)
--   descartado  -> rejeitado  (semanticamente equivalente)
--   revisado    -> pendente   (ainda em andamento)
--   ativo       -> pendente   (ainda em andamento)

BEGIN;

-- 1. Remover constraints que referenciam o enum antigo
ALTER TABLE registros DROP CONSTRAINT IF EXISTS ck_registros_consolidado_campos_basicos;
ALTER TABLE registros DROP CONSTRAINT IF EXISTS ck_registros_aprovado_campos_basicos;

-- 2. Converter coluna para TEXT para permitir migração de dados sem depender do enum
ALTER TABLE registros ALTER COLUMN status DROP DEFAULT;
ALTER TABLE registros ALTER COLUMN status TYPE TEXT USING status::TEXT;

-- 3. Migrar dados
UPDATE registros SET status = 'aprovado'  WHERE status = 'consolidado';
UPDATE registros SET status = 'rejeitado' WHERE status = 'descartado';
UPDATE registros SET status = 'pendente'  WHERE status IN ('revisado', 'ativo');

-- 4. Recriar o tipo enum com os novos valores
DROP TYPE IF EXISTS registro_status;
CREATE TYPE registro_status AS ENUM ('pendente', 'aprovado', 'rejeitado');

-- 5. Converter coluna de volta para o enum
ALTER TABLE registros
    ALTER COLUMN status TYPE registro_status USING status::registro_status;
ALTER TABLE registros ALTER COLUMN status SET NOT NULL;
ALTER TABLE registros ALTER COLUMN status SET DEFAULT 'pendente'::registro_status;

-- 6. Recriar constraint usando o novo valor 'aprovado'
ALTER TABLE registros
ADD CONSTRAINT ck_registros_aprovado_campos_basicos
CHECK (
    status <> 'aprovado'
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
