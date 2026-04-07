-- Remover tabelas na ordem correta (dependência de FK)
DROP TABLE IF EXISTS alert_reads;
DROP TABLE IF EXISTS alerts;

-- Remover tipos enum (se não estiverem em uso)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_status') THEN
        DROP TYPE alert_status;
    END IF;

    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_severity') THEN
        DROP TYPE alert_severity;
    END IF;

    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_type') THEN
        DROP TYPE alert_type;
    END IF;
END $$;
