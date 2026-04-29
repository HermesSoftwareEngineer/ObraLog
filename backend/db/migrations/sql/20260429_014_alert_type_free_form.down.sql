DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_type') THEN
    CREATE TYPE alert_type AS ENUM ('maquina_quebrada', 'acidente', 'falta_material', 'risco_seguranca', 'outro');
  END IF;
END $$;

ALTER TABLE alerts
  ALTER COLUMN type TYPE alert_type
  USING (
    CASE
      WHEN replace(trim(lower(type)), ' ', '_') IN ('maquina_quebrada', 'acidente', 'falta_material', 'risco_seguranca', 'outro')
        THEN replace(trim(lower(type)), ' ', '_')::alert_type
      ELSE 'outro'::alert_type
    END
  );

ALTER TABLE alert_type_aliases
  ALTER COLUMN canonical_type TYPE alert_type
  USING (
    CASE
      WHEN replace(trim(lower(canonical_type)), ' ', '_') IN ('maquina_quebrada', 'acidente', 'falta_material', 'risco_seguranca', 'outro')
        THEN replace(trim(lower(canonical_type)), ' ', '_')::alert_type
      ELSE 'outro'::alert_type
    END
  );

ALTER TABLE alerts
  DROP CONSTRAINT IF EXISTS ck_alerts_type_not_empty;

ALTER TABLE alert_type_aliases
  DROP CONSTRAINT IF EXISTS ck_alert_type_aliases_canonical_type_not_empty;
