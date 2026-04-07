ALTER TABLE alerts DROP COLUMN IF EXISTS obra_id;
ALTER TABLE alerts DROP COLUMN IF EXISTS equipment_code;
DROP INDEX IF EXISTS idx_alerts_obra_id;
