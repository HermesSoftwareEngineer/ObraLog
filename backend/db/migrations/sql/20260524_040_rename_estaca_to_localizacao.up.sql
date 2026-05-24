-- Migration 040: Rename estaca (text) to localizacao in registros table
-- and rename the campos_ativos key "estaca" to "localizacao" in registro_schemas.
--
-- Context:
-- The column registros.estaca stored free-text location descriptions.
-- It was misleadingly named after the numeric stake system ("estaca").
-- Renamed to "localizacao" for clarity.
--
-- The campos_ativos JSONB key "estaca" in registro_schemas referred to the
-- same text field. Renamed consistently to "localizacao".
--
-- NOTE: "estaca_inicial", "estaca_final" (numeric stake fields) are NOT renamed.
-- The location_type enum value "estaca" (profile type for numeric stakes) is also NOT changed.

-- 1. Rename column in registros
ALTER TABLE registros RENAME COLUMN estaca TO localizacao;

-- 2. Rename key in registro_schemas.campos_ativos JSON
UPDATE registro_schemas
SET campos_ativos = (campos_ativos - 'estaca') || jsonb_build_object('localizacao', (campos_ativos->>'estaca')::boolean)
WHERE campos_ativos ? 'estaca';
