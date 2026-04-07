-- Tornar observacao opcional em registros
ALTER TABLE registros
ALTER COLUMN observacao DROP NOT NULL;
