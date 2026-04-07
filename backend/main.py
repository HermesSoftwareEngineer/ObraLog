import os
import threading
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

try:
    from .api.routes.webhook import telegram_blueprint
    from .api.routes.crud import api_blueprint
    from .api.routes.diario import router as diario_router
    from .api.routes.alerts import router as alerts_router
    from .api.routes.reports import router as reports_blueprint
    from .api.routes.auth import auth_blueprint
    from .services.telegram import start_polling, set_webhook
except ImportError:
    from api.routes.webhook import telegram_blueprint
    from api.routes.crud import api_blueprint
    from api.routes.diario import router as diario_router
    from api.routes.alerts import router as alerts_router
    from api.routes.reports import router as reports_blueprint
    from api.routes.auth import auth_blueprint
    from services.telegram import start_polling, set_webhook


app = Flask(__name__)

UPLOAD_DIR = Path(os.environ.get("REGISTRO_IMAGENS_DIR", str(Path("backend") / "uploads" / "registros")))


def _parse_cors_origins() -> list[str]:
    raw_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    origins = [item.strip() for item in raw_origins.split(",") if item.strip()]
    return origins or ["http://localhost:5173"]

CORS(
    app,
    resources={
        r"/api/*": {"origins": _parse_cors_origins()},
        r"/backend/uploads/*": {"origins": _parse_cors_origins()},
    },
    supports_credentials=True,
)

app.register_blueprint(telegram_blueprint)
app.register_blueprint(api_blueprint)
app.register_blueprint(diario_router)
app.register_blueprint(alerts_router)
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
elif os.environ.get("TELEGRAM_POLLING_IN_DEV", "true").lower() not in {"1", "true", "yes", "on"}:
    public_url = os.environ.get("PUBLIC_BASE_URL")
    if public_url:
        try:
            set_webhook(public_url)
            app.logger.info(f"Telegram webhook configurado automaticamente para a URL: {public_url}")
        except Exception as e:
            app.logger.error(f"Erro ao configurar webhook automaticamente: {e}")
    else:
        app.logger.warning("TELEGRAM_POLLING_IN_DEV desativado, mas PUBLIC_BASE_URL não está configurada. Webhook automático ignorado.")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/")
def index():
    return jsonify({"message": "Agente de Diário de Obra backend ativo"})


@app.get("/backend/uploads/registros/<path:filename>")
def download_registro_image(filename: str):
    normalized = Path((filename or "").replace("\\", "/")).name
    if not normalized:
        return jsonify({"ok": False, "error": "Nome de arquivo inválido."}), 400

    target = UPLOAD_DIR / normalized
    if not target.exists() or not target.is_file():
        return jsonify({"ok": False, "error": "Imagem não encontrada."}), 404

    return send_from_directory(UPLOAD_DIR.resolve(), normalized)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
