-- Reverter observacao para obrigatoria em registros
UPDATE registros
SET observacao = ''
WHERE observacao IS NULL;

ALTER TABLE registros
ALTER COLUMN observacao SET NOT NULL;
