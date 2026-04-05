#!/usr/bin/env python
"""Standalone Telegram bot poller para desenvolvimento em localhost."""

import sys
import logging
from pathlib import Path

# Adicionar raiz do projeto ao path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# Carrega .env do raiz do projeto
load_dotenv(project_root / ".env")

try:
    from backend.services.telegram import start_polling
except ImportError:
    # Fallback se rodado a partir do diretório backends ou agents
    sys.path.insert(0, str(project_root / "backend"))
    from services.telegram import start_polling

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    start_polling()
