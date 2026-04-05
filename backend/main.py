import os
import threading

from flask import Flask, jsonify
from flask_cors import CORS

try:
    from .api.routes.webhook import telegram_blueprint
    from .api.routes.crud import api_blueprint
    from .api.routes.reports import router as reports_blueprint
    from .api.routes.auth import auth_blueprint
    from .services.telegram import start_polling
except ImportError:
    from api.routes.webhook import telegram_blueprint
    from api.routes.crud import api_blueprint
    from api.routes.reports import router as reports_blueprint
    from api.routes.auth import auth_blueprint
    from services.telegram import start_polling


app = Flask(__name__)


def _get_cors_origins():
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:5174")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


CORS(
    app,
    resources={r"/api/*": {"origins": _get_cors_origins()}},
    supports_credentials=True,
)

app.register_blueprint(telegram_blueprint)
app.register_blueprint(api_blueprint)
app.register_blueprint(reports_blueprint)
app.register_blueprint(auth_blueprint)


def _should_start_polling_in_dev() -> bool:
    debug_enabled = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes", "on"}
    polling_enabled = os.environ.get("TELEGRAM_POLLING_IN_DEV", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    reloader_main = os.environ.get("WERKZEUG_RUN_MAIN")
    if not polling_enabled:
        return False

    # With flask --debug, only start polling in the reloader child process.
    if debug_enabled:
        return reloader_main == "true"

    # Without debug/reloader (e.g., python backend/main.py), start normally.
    return reloader_main is None


if _should_start_polling_in_dev():
    polling_thread = threading.Thread(target=start_polling, name="telegram-polling", daemon=True)
    polling_thread.start()
    app.logger.info("Telegram polling iniciado automaticamente em modo desenvolvimento.")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/")
def index():
    return jsonify({"message": "Agente de Diário de Obra backend ativo"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
