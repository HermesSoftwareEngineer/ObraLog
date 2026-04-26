from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.core.config import settings


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://") and "+" not in database_url.split("://", 1)[0]:
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


engine = create_engine(_normalize_database_url(settings.database_url), pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def ensure_runtime_migrations() -> None:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telefone VARCHAR"))
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_telefone_unique ON usuarios(telefone) WHERE telefone IS NOT NULL"
            )
        )
        connection.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR"))
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_telegram_chat_id ON usuarios(telegram_chat_id)"
            )
        )
        connection.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telegram_thread_id VARCHAR"))
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_telegram_thread_id_unique ON usuarios(telegram_thread_id) WHERE telegram_thread_id IS NOT NULL"
            )
        )
        connection.execute(
            text(
                """
                UPDATE usuarios
                SET telegram_thread_id = telegram_chat_id
                WHERE telegram_thread_id IS NULL
                  AND telegram_chat_id IS NOT NULL
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS telegram_link_codes (
                    id SERIAL PRIMARY KEY,
                    user_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                    code VARCHAR(32) NOT NULL UNIQUE,
                    generated_by_user_id INT REFERENCES usuarios(id) ON DELETE SET NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used_at TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_telegram_link_codes_user ON telegram_link_codes(user_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_telegram_link_codes_expires_at ON telegram_link_codes(expires_at)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_telegram_link_codes_used_at ON telegram_link_codes(used_at)"))
        connection.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_type t
                        JOIN pg_enum e ON e.enumtypid = t.oid
                        WHERE t.typname = 'lado_pista_enum'
                          AND e.enumlabel = 'direita'
                    ) THEN
                        ALTER TYPE lado_pista_enum RENAME VALUE 'direita' TO 'direito';
                    END IF;

                    IF EXISTS (
                        SELECT 1
                        FROM pg_type t
                        JOIN pg_enum e ON e.enumtypid = t.oid
                        WHERE t.typname = 'lado_pista_enum'
                          AND e.enumlabel = 'esquerda'
                    ) THEN
                        ALTER TYPE lado_pista_enum RENAME VALUE 'esquerda' TO 'esquerdo';
                    END IF;
                END $$;
                """
            )
        )
        connection.execute(text("ALTER TABLE registros ADD COLUMN IF NOT EXISTS raw_text TEXT"))
        connection.execute(text("ALTER TABLE registros ADD COLUMN IF NOT EXISTS source_message_id UUID"))
        connection.execute(text("ALTER TABLE registros ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
        connection.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'registro_status') THEN
                        CREATE TYPE registro_status AS ENUM ('pendente', 'consolidado', 'revisado', 'ativo', 'descartado');
                    END IF;
                END $$;
                """
            )
        )
        connection.execute(text("ALTER TABLE registros ADD COLUMN IF NOT EXISTS status registro_status DEFAULT 'pendente'"))
        connection.execute(text("UPDATE registros SET status = 'pendente' WHERE status IS NULL"))
        connection.execute(text("ALTER TABLE registros ALTER COLUMN status SET NOT NULL"))
        connection.execute(text("ALTER TABLE registros ALTER COLUMN data DROP NOT NULL"))
        connection.execute(text("ALTER TABLE registros ALTER COLUMN frente_servico_id DROP NOT NULL"))
        connection.execute(text("ALTER TABLE registros ALTER COLUMN usuario_registrador_id DROP NOT NULL"))
        connection.execute(text("ALTER TABLE registros ALTER COLUMN estaca_inicial DROP NOT NULL"))
        connection.execute(text("ALTER TABLE registros ALTER COLUMN estaca_final DROP NOT NULL"))
        connection.execute(text("ALTER TABLE registros ALTER COLUMN resultado DROP NOT NULL"))
        connection.execute(text("ALTER TABLE registros ALTER COLUMN tempo_manha DROP NOT NULL"))
        connection.execute(text("ALTER TABLE registros ALTER COLUMN tempo_tarde DROP NOT NULL"))
        connection.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'registros'
                          AND column_name = 'pista'
                    ) THEN
                        UPDATE registros
                        SET lado_pista = pista
                        WHERE lado_pista IS NULL
                          AND pista IS NOT NULL;

                        ALTER TABLE registros DROP COLUMN pista;
                    END IF;
                END $$;
                """
            )
        )
        connection.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'registros_usuario_registrador_id_fkey'
                    ) THEN
                        ALTER TABLE registros DROP CONSTRAINT registros_usuario_registrador_id_fkey;
                    END IF;

                    ALTER TABLE registros
                    ADD CONSTRAINT registros_usuario_registrador_id_fkey
                    FOREIGN KEY (usuario_registrador_id) REFERENCES usuarios(id) ON DELETE RESTRICT;
                END $$;
                """
            )
        )
        connection.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'registros_source_message_id_fkey'
                    ) THEN
                        ALTER TABLE registros DROP CONSTRAINT registros_source_message_id_fkey;
                    END IF;
                END $$;
                """
            )
        )
        connection.execute(text("ALTER TABLE registros DROP CONSTRAINT IF EXISTS ck_registros_required_fields"))
        connection.execute(text("ALTER TABLE registros DROP CONSTRAINT IF EXISTS ck_registros_consolidado_campos_basicos"))
        connection.execute(
            text(
                """
                ALTER TABLE registros
                ADD CONSTRAINT ck_registros_consolidado_campos_basicos
                CHECK (
                    status <> 'consolidado'
                    OR (
                        data IS NOT NULL
                        AND frente_servico_id IS NOT NULL
                        AND usuario_registrador_id IS NOT NULL
                        AND estaca_inicial IS NOT NULL
                        AND estaca_final IS NOT NULL
                        AND resultado IS NOT NULL
                        AND tempo_manha IS NOT NULL
                        AND tempo_tarde IS NOT NULL
                    )
                ) NOT VALID
                """
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_registros_status ON registros(status)"))
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS registro_imagens (
                    id SERIAL PRIMARY KEY,
                    registro_id INT NOT NULL REFERENCES registros(id) ON DELETE CASCADE,
                    storage_path VARCHAR NULL,
                    external_url VARCHAR NULL,
                    mime_type VARCHAR NULL,
                    file_size INT NULL,
                    origem VARCHAR NOT NULL DEFAULT 'api',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_registro_imagens_registro ON registro_imagens(registro_id)"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        connection.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'canal_origem_mensagem') THEN
                        CREATE TYPE canal_origem_mensagem AS ENUM ('telegram');
                    END IF;

                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'conteudo_mensagem_tipo') THEN
                        CREATE TYPE conteudo_mensagem_tipo AS ENUM ('texto', 'foto', 'audio', 'misto');
                    END IF;

                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'processamento_mensagem_status') THEN
                        CREATE TYPE processamento_mensagem_status AS ENUM ('pendente', 'processada', 'erro');
                    END IF;
                END $$;
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS mensagens_campo (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    canal canal_origem_mensagem NOT NULL,
                    telegram_chat_id VARCHAR,
                    telegram_message_id BIGINT,
                    telegram_update_id BIGINT,
                    usuario_id INT REFERENCES usuarios(id) ON DELETE SET NULL,
                    recebida_em TIMESTAMPTZ NOT NULL DEFAULT now(),
                    tipo_conteudo conteudo_mensagem_tipo NOT NULL DEFAULT 'texto',
                    texto_bruto TEXT,
                    texto_normalizado TEXT,
                    payload_json TEXT,
                    hash_idempotencia VARCHAR(120) UNIQUE,
                    processada_em TIMESTAMPTZ,
                    status_processamento processamento_mensagem_status NOT NULL DEFAULT 'pendente',
                    erro_processamento TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS registro_auditoria (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    registro_id INT NOT NULL REFERENCES registros(id) ON DELETE CASCADE,
                    acao VARCHAR(30) NOT NULL,
                    diff_json TEXT NOT NULL,
                    actor_user_id INT REFERENCES usuarios(id) ON DELETE SET NULL,
                    actor_level VARCHAR(30),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        connection.execute(text("ALTER TABLE registros ADD CONSTRAINT registros_source_message_id_fkey FOREIGN KEY (source_message_id) REFERENCES mensagens_campo(id) ON DELETE SET NULL"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_mensagens_campo_telegram_msg ON mensagens_campo(canal, telegram_chat_id, telegram_message_id) WHERE telegram_message_id IS NOT NULL"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_mensagens_campo_status ON mensagens_campo(status_processamento)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_mensagens_campo_recebida_em ON mensagens_campo(recebida_em)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_registro_auditoria_registro ON registro_auditoria(registro_id)"))
        connection.execute(text("DROP INDEX IF EXISTS idx_lancamento_midias_lancamento"))
        connection.execute(text("DROP INDEX IF EXISTS idx_lancamento_recursos_lancamento"))
        connection.execute(text("DROP INDEX IF EXISTS idx_lancamento_itens_lancamento"))
        connection.execute(text("DROP INDEX IF EXISTS idx_lancamentos_diario_status"))
        connection.execute(text("DROP INDEX IF EXISTS idx_lancamentos_diario_data"))
        connection.execute(text("DROP TABLE IF EXISTS lancamento_midias"))
        connection.execute(text("DROP TABLE IF EXISTS lancamento_recursos"))
        connection.execute(text("DROP TABLE IF EXISTS lancamento_itens"))
        connection.execute(text("DROP TABLE IF EXISTS lancamentos_diario"))
        connection.execute(text("DROP TYPE IF EXISTS recurso_categoria"))
        connection.execute(text("DROP TYPE IF EXISTS lancamento_tipo_item"))
        connection.execute(text("DROP TYPE IF EXISTS lancamento_status"))
        connection.execute(
            text(
                """
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
                """
            )
        )
        connection.execute(
            text(
                """
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
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS alert_reads (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    alert_id UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
                    worker_id INT NOT NULL REFERENCES usuarios(id),
                    read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (alert_id, worker_id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS alert_type_aliases (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    alias VARCHAR(120) NOT NULL UNIQUE,
                    normalized_alias VARCHAR(120) NOT NULL UNIQUE,
                    canonical_type alert_type NOT NULL,
                    descricao TEXT,
                    ativo BOOLEAN NOT NULL DEFAULT true,
                    created_by INT REFERENCES usuarios(id) ON DELETE SET NULL,
                    updated_by INT REFERENCES usuarios(id) ON DELETE SET NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_alerts_code ON alerts(code)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_alerts_reported_by ON alerts(reported_by)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_alert_reads_alert_id ON alert_reads(alert_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_alert_reads_worker_id ON alert_reads(worker_id)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_type_aliases_alias_unique ON alert_type_aliases(alias)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_type_aliases_normalized_alias_unique ON alert_type_aliases(normalized_alias)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_alert_type_aliases_canonical_type ON alert_type_aliases(canonical_type)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_alert_type_aliases_ativo ON alert_type_aliases(ativo)"))


ensure_runtime_migrations()


def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
