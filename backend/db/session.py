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
        connection.execute(text("ALTER TABLE registros DROP CONSTRAINT IF EXISTS ck_registros_required_fields"))
        connection.execute(
            text(
                """
                ALTER TABLE registros
                ADD CONSTRAINT ck_registros_required_fields
                CHECK (
                    data IS NOT NULL
                    AND frente_servico_id IS NOT NULL
                    AND usuario_registrador_id IS NOT NULL
                    AND estaca_inicial IS NOT NULL
                    AND estaca_final IS NOT NULL
                    AND resultado IS NOT NULL
                    AND tempo_manha IS NOT NULL
                    AND tempo_tarde IS NOT NULL
                    AND observacao IS NOT NULL
                ) NOT VALID
                """
            )
        )
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


ensure_runtime_migrations()


def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
