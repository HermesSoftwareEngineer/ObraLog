import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def get_ambiente() -> str:
    """Retorna 'dev' ou 'prod' com base na variável OBRALOG_ENV (ou ENV / FLASK_ENV)."""
    raw = (
        os.environ.get("OBRALOG_ENV")
        or os.environ.get("ENV")
        or os.environ.get("FLASK_ENV")
        or "prod"
    ).strip().lower()
    return "dev" if raw in {"development", "dev"} else "prod"


class Settings(BaseSettings):
    google_api_key: str
    telegram_token: str | None = None
    database_url: str
    redis_url: str | None = None

    # Supabase Storage — required for PDF upload in diários sprint.
    # Create the bucket "diarios" manually in the Supabase Storage panel before use.
    supabase_url: str | None = None
    supabase_service_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
