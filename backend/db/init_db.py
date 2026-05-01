#!/usr/bin/env python
"""Script para inicializar o schema no Supabase."""

import sys
from pathlib import Path

# Adicionar raiz do projeto ao path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(project_root / ".env")

from backend.db.models import Base
from backend.core.config import settings


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://") and "+" not in database_url.split("://", 1)[0]:
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url

def init_db():
    """Cria as tabelas no banco de dados."""
    engine = create_engine(_normalize_database_url(settings.database_url))
    
    try:
        Base.metadata.create_all(bind=engine)

        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS obras (
                        id SERIAL PRIMARY KEY,
                        nome VARCHAR(200) NOT NULL,
                        codigo VARCHAR(80),
                        descricao TEXT,
                        ativo BOOLEAN NOT NULL DEFAULT true,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        tenant_id INT NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
                        CONSTRAINT uq_obras_codigo_tenant UNIQUE (tenant_id, codigo)
                    )
                    """
                )
            )
            connection.execute(text("ALTER TABLE registros ADD COLUMN IF NOT EXISTS obra_id INT REFERENCES obras(id) ON DELETE SET NULL"))
            connection.execute(text("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS obra_id INT REFERENCES obras(id) ON DELETE SET NULL"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_obras_tenant_id ON obras(tenant_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_registros_obra_id ON registros(obra_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS idx_alerts_obra_id ON alerts(obra_id)"))
            connection.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS location_type VARCHAR(50)"))
            connection.execute(text("ALTER TABLE tenants ALTER COLUMN location_type SET DEFAULT 'estaca'"))
            connection.execute(text("UPDATE tenants SET location_type = 'estaca' WHERE location_type IS NULL"))
            connection.execute(text("ALTER TABLE tenants ALTER COLUMN location_type SET NOT NULL"))
            connection.execute(text("ALTER TABLE registros ALTER COLUMN observacao DROP NOT NULL"))
            connection.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telefone VARCHAR"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_telefone_unique ON usuarios(telefone) WHERE telefone IS NOT NULL"))
            connection.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_telegram_chat_id ON usuarios(telegram_chat_id)"))
            connection.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telegram_thread_id VARCHAR"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_telegram_thread_id_unique ON usuarios(telegram_thread_id) WHERE telegram_thread_id IS NOT NULL"))
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
        
        print("Schema criado com sucesso no Supabase.")
        return True
    except Exception as exc:
        print(f"Erro ao criar schema: {exc}")
        return False
    finally:
        engine.dispose()

if __name__ == "__main__":
    success = init_db()
    sys.exit(0 if success else 1)
