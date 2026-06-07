import logging
import os
import sys
import warnings


def _parse_level(value: str | None, default: int = logging.INFO) -> int:
    raw = str(value or "").strip().upper()
    if raw in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
        return getattr(logging, raw)
    return default


ROOT_LEVEL = _parse_level(os.environ.get("OBRALOG_LOG_LEVEL"), logging.INFO)

logging.basicConfig(
    level=ROOT_LEVEL,
    format="[%(asctime)s] %(levelname)s in %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Cloud Run console: somente WARNING+ para reduzir ruído
_stream_handler = logging.getLogger().handlers[0]
_stream_handler.setLevel(logging.WARNING)
_stream_handler.flush = sys.stdout.flush

# Persistência estruturada no Firestore (ROOT_LEVEL+, CRITICAL dispara e-mail)
if os.getenv("GCP_PROJECT_ID"):
    from backend.logging.firestore_handler import FirestoreHandler, LogContextFilter
    _fs_handler = FirestoreHandler(
        collection=os.getenv("FIRESTORE_COLLECTION", "logs"),
        ttl_days=90,
    )
    _fs_handler.setLevel(ROOT_LEVEL)
    logging.getLogger().addHandler(_fs_handler)
    logging.getLogger().addFilter(LogContextFilter())

# Keep third-party network/tracing noise out of the console by default.
for noisy_name in (
    "httpcore",
    "httpx",
    "telegram",
    "urllib3",
    "asyncio",
    "langsmith",
    "google",
):
    logging.getLogger(noisy_name).setLevel(logging.WARNING)

# Keep API and Telegram service visibility for operational monitoring.
logging.getLogger("werkzeug").setLevel(logging.INFO)
logging.getLogger("backend.services.telegram").setLevel(logging.INFO)
logging.getLogger("backend.services.telegram_processor").setLevel(logging.INFO)
logging.getLogger("backend.main").setLevel(logging.INFO)

# Silence known noisy warning from langchain on Python >= 3.14.
warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
    category=UserWarning,
)

logger = logging.getLogger("diario_obra")
logger.setLevel(ROOT_LEVEL)
