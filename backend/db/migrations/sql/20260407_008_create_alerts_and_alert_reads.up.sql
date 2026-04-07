-- Criar enums de alertas
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_type') THEN
        CREATE TYPE alert_type AS ENUM ('maquina_quebrada', 'acidente', 'falta_material', 'risco_seguranca', 'outro');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_severity') THEN
        CREATE TYPE alert_severity AS ENUM ('baixa', 'media', 'alta', 'critica');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_status') THEN
        CREATE TYPE alert_status AS ENUM ('aberto', 'em_atendimento', 'aguardando_peca', 'resolvido', 'cancelado');
    END IF;
END $$;

-- Criar tabela de alertas
CREATE TABLE IF NOT EXISTS alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code VARCHAR(20) UNIQUE NOT NULL,
  type alert_type NOT NULL,
  severity alert_severity NOT NULL,
  reported_by INT NOT NULL REFERENCES usuarios(id),
  telegram_message_id BIGINT,
  title VARCHAR(200) NOT NULL,
  description TEXT NOT NULL,
  raw_text TEXT,
  location_detail VARCHAR(200),
  equipment_name VARCHAR(100),
  photo_urls TEXT[],
  status alert_status NOT NULL DEFAULT 'aberto',
  priority_score SMALLINT,
  notified_at TIMESTAMPTZ,
  notified_channels TEXT[],
  resolved_by INT REFERENCES usuarios(id),
  resolved_at TIMESTAMPTZ,
  resolution_notes TEXT,
  is_read BOOLEAN NOT NULL DEFAULT false,
  read_at TIMESTAMPTZ,
  read_by INT REFERENCES usuarios(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Criar tabela de leituras de alerta
CREATE TABLE IF NOT EXISTS alert_reads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  alert_id UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
  worker_id INT NOT NULL REFERENCES usuarios(id),
  read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (alert_id, worker_id)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_alerts_code ON alerts(code);
CREATE INDEX IF NOT EXISTS idx_alerts_reported_by ON alerts(reported_by);
CREATE INDEX IF NOT EXISTS idx_alert_reads_alert_id ON alert_reads(alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_reads_worker_id ON alert_reads(worker_id);
