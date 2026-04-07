ALTER TABLE alerts ADD COLUMN IF NOT EXISTS obra_id INT REFERENCES frentes_servico(id);
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS equipment_code VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_alerts_obra_id ON alerts(obra_id);
