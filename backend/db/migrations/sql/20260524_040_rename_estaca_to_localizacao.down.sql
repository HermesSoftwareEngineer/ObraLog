-- Migration 040 rollback: Revert localizacao back to estaca

ALTER TABLE registros RENAME COLUMN localizacao TO estaca;

UPDATE registro_schemas
SET campos_ativos = (campos_ativos - 'localizacao') || jsonb_build_object('estaca', (campos_ativos->>'localizacao')::boolean)
WHERE campos_ativos ? 'localizacao';
