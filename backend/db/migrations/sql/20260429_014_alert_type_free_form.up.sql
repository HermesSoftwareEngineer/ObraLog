ALTER TABLE alert_type_aliases
  ALTER COLUMN canonical_type TYPE VARCHAR(120)
  USING canonical_type::text;

ALTER TABLE alerts
  ALTER COLUMN type TYPE VARCHAR(120)
  USING type::text;

UPDATE alert_type_aliases
SET canonical_type = replace(trim(lower(canonical_type)), ' ', '_')
WHERE canonical_type IS NOT NULL;

UPDATE alerts
SET type = replace(trim(lower(type)), ' ', '_')
WHERE type IS NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ck_alert_type_aliases_canonical_type_not_empty'
  ) THEN
    ALTER TABLE alert_type_aliases
      ADD CONSTRAINT ck_alert_type_aliases_canonical_type_not_empty
      CHECK (length(trim(canonical_type)) > 0);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ck_alerts_type_not_empty'
  ) THEN
    ALTER TABLE alerts
      ADD CONSTRAINT ck_alerts_type_not_empty
      CHECK (length(trim(type)) > 0);
  END IF;
END $$;

DROP TYPE IF EXISTS alert_type;
