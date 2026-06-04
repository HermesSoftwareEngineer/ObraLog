import logging
import os
import threading
from pathlib import Path

# Permite event loops aninhados — necessário porque google-genai usa httpx/asyncio
# internamente e gunicorn gthread não tem event loop por padrão em cada thread.
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from backend.core.logger import logger as core_logger

_startup_logger = logging.getLogger("obralog.startup")

try:
    from .api.routes.webhook import telegram_blueprint
    from .api.routes.whatsapp_webhook import whatsapp_blueprint
    from .api.routes.crud import api_blueprint
    from .api.routes.diario import router as diario_router, diarios_router, diarios_files_router
    from .api.routes.alerts import router as alerts_router
    from .api.routes.reports import router as reports_blueprint
    from .api.routes.auth import auth_blueprint
    from .api.routes.chat import router as chat_router
    from .api.routes.tenant import tenant_blueprint
    from .api.routes.dashboard import dashboard_blueprint
    from .api.routes.admin import admin_blueprint
    from .api.routes.creditos import creditos_v1
    from .api.routes.agent_events import router as agent_events_router
    from .services.telegram import start_polling, set_webhook
except ImportError:
    from api.routes.webhook import telegram_blueprint
    from api.routes.whatsapp_webhook import whatsapp_blueprint
    from api.routes.crud import api_blueprint
    from api.routes.diario import router as diario_router, diarios_router, diarios_files_router
    from api.routes.alerts import router as alerts_router
    from api.routes.reports import router as reports_blueprint
    from api.routes.auth import auth_blueprint
    from api.routes.chat import router as chat_router
    from api.routes.tenant import tenant_blueprint
    from api.routes.dashboard import dashboard_blueprint
    from api.routes.admin import admin_blueprint
    from api.routes.creditos import creditos_v1
    from api.routes.agent_events import router as agent_events_router
    from services.telegram import start_polling, set_webhook


app = Flask(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent  # ObraLog/backend/
UPLOAD_DIR = Path(os.environ.get("REGISTRO_IMAGENS_DIR", str(_BACKEND_DIR / "uploads" / "registros")))


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
app.register_blueprint(whatsapp_blueprint)
app.register_blueprint(api_blueprint)
app.register_blueprint(diario_router)
app.register_blueprint(diarios_router)
app.register_blueprint(diarios_files_router)
app.register_blueprint(alerts_router)
app.register_blueprint(reports_blueprint)
app.register_blueprint(auth_blueprint)
app.register_blueprint(chat_router)
app.register_blueprint(tenant_blueprint)
app.register_blueprint(dashboard_blueprint)
app.register_blueprint(admin_blueprint)
app.register_blueprint(creditos_v1)
app.register_blueprint(agent_events_router)


def _is_werkzeug_reloader_parent() -> bool:
    """Retorna True se este processo é o pai do Werkzeug (não deve iniciar threads únicas)."""
    import sys
    is_flask_cli = "flask" in sys.argv[0].lower() or os.environ.get("FLASK_RUN_FROM_CLI") == "true"
    has_reloader = (
        any(arg in sys.argv for arg in ["--debug", "--reload", "-d"])
        or os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes", "on"}
        or os.environ.get("FLASK_ENV", "").lower() == "development"
    )
    if is_flask_cli and has_reloader:
        # Werkzeug sobe um processo pai + processo filho. Só o filho tem WERKZEUG_RUN_MAIN=true.
        return os.environ.get("WERKZEUG_RUN_MAIN") != "true"
    return False


# TELEGRAM_MODE=polling  → bot busca atualizações ativamente (não precisa de URL pública)
# TELEGRAM_MODE=webhook  → Telegram envia updates para PUBLIC_BASE_URL/telegram/webhook
# Padrão: polling (funciona em qualquer ambiente sem configuração extra)
_telegram_mode = os.environ.get("TELEGRAM_MODE", "polling").strip().lower()
_bot_channel   = os.environ.get("BOT_CHANNEL",    "telegram").strip().lower()

app.logger.info(
    "Canal de bot: BOT_CHANNEL=%s TELEGRAM_MODE=%s",
    _bot_channel, _telegram_mode if _bot_channel == "telegram" else "n/a",
)

if _bot_channel == "telegram":
    if _telegram_mode == "polling":
        if _is_werkzeug_reloader_parent():
            app.logger.info("Telegram polling aguardando processo filho do Werkzeug.")
        else:
            polling_thread = threading.Thread(target=start_polling, name="telegram-polling", daemon=True)
            polling_thread.start()
            app.logger.info("Telegram polling iniciado (TELEGRAM_MODE=polling).")

    elif _telegram_mode == "webhook":
        public_url = os.environ.get("PUBLIC_BASE_URL", "").strip()
        if public_url:
            try:
                set_webhook(public_url)
            except Exception as exc:
                app.logger.error(
                    "FALHA ao registrar webhook do Telegram — agente nao receberá mensagens: %s", exc
                )
        else:
            app.logger.error(
                "TELEGRAM_MODE=webhook mas PUBLIC_BASE_URL nao está configurada — agente nao receberá mensagens."
            )
    else:
        app.logger.error("TELEGRAM_MODE inválido: '%s'. Use 'polling' ou 'webhook'.", _telegram_mode)


elif _bot_channel == "whatsapp":
    app.logger.info(
        "Canal WhatsApp ativo. Webhook disponível em POST /whatsapp/webhook. "
        "Configure-o no Meta Developers apontando para: %s/whatsapp/webhook",
        os.environ.get("PUBLIC_BASE_URL", "<PUBLIC_BASE_URL>"),
    )
else:
    app.logger.error(
        "BOT_CHANNEL inválido ou não reconhecido: '%s'. Use 'telegram' ou 'whatsapp'.", _bot_channel
    )


def _run_encerrar_conversas_loop(interval_seconds: int = 600) -> None:
    import time
    from backend.jobs.encerrar_conversas import run as _encerrar

    while True:
        try:
            _encerrar()
        except Exception as exc:
            app.logger.error("Erro no job encerrar_conversas: %s", exc)
        time.sleep(interval_seconds)


def _start_encerrar_conversas_scheduler() -> None:
    # Flush imediato ao subir + loop periódico a cada 10 min
    t = threading.Thread(
        target=_run_encerrar_conversas_loop,
        name="encerrar-conversas-scheduler",
        daemon=True,
    )
    t.start()
    app.logger.info("Scheduler de encerramento de conversas iniciado (intervalo: 10 min).")


_start_encerrar_conversas_scheduler()


def _warmup_agent_tools() -> None:
    """Pré-inicializa modelos Pydantic das tools e cliente LLM no processo principal.

    Sem isso, a primeira chamada em qualquer thread gunicorn demora ~100s porque:
    1. @tool decorator recria modelos Pydantic para 40+ ferramentas (cold-start Pydantic)
    2. google-genai SDK inicializa httpx.AsyncClient lazy na primeira chamada
    Ao rodar no processo principal (thread main), o event loop asyncio existe e o
    nest_asyncio já foi aplicado — inicialização é limpa e rápida.
    """
    try:
        import time as _time
        _t0 = _time.monotonic()
        _startup_logger.info("[WARMUP] iniciando")

        _t = _time.monotonic()
        from backend.agents.nodes._tool_utils import resolve_tool_map
        from backend.agents.llms import llm_main
        _startup_logger.info("[WARMUP] imports=%.2fs", _time.monotonic() - _t)

        dummy_config = {"configurable": {
            "actor_user_id": 0, "actor_level": "campo",
            "tenant_id": None, "obra_id_ativa": None,
            "telegram_chat_id": "warmup",
        }}

        _t = _time.monotonic()
        tool_map = resolve_tool_map(dummy_config)
        _startup_logger.info("[WARMUP] resolve_tool_map=%.2fs tools=%d", _time.monotonic() - _t, len(tool_map))

        _t = _time.monotonic()
        llm_main.bind_tools(list(tool_map.values()))
        _startup_logger.info("[WARMUP] bind_tools=%.2fs", _time.monotonic() - _t)

        _t = _time.monotonic()
        llm_main.invoke("ok")
        _startup_logger.info("[WARMUP] llm_invoke=%.2fs", _time.monotonic() - _t)

        _startup_logger.info("[WARMUP] concluído total=%.2fs tools=%d", _time.monotonic() - _t0, len(tool_map))
    except Exception as exc:
        import traceback
        _startup_logger.warning("[WARMUP] FALHOU: %s\n%s", exc, traceback.format_exc())


_warmup_agent_tools()


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/diag/connectivity")
def diag_connectivity():
    """Testa conectividade outbound de dentro do container. Remover após investigação."""
    import time
    import urllib.request
    import ssl

    results = {}

    # 1. Supabase — conexão TCP+SSL direta
    db_url = os.environ.get("DATABASE_URL", "")
    try:
        import psycopg
        t = time.monotonic()
        with psycopg.connect(db_url, connect_timeout=10) as conn:
            conn.execute("SELECT 1")
        results["supabase_direct"] = {"ok": True, "ms": round((time.monotonic() - t) * 1000)}
    except Exception as exc:
        results["supabase_direct"] = {"ok": False, "error": str(exc)[:200]}

    # 2. Google APIs SSL
    for label, url in [
        ("google_apis", "https://generativelanguage.googleapis.com"),
        ("langsmith",   "https://api.smith.langchain.com/info"),
    ]:
        try:
            t = time.monotonic()
            ctx = ssl.create_default_context()
            try:
                req = urllib.request.urlopen(url, context=ctx, timeout=10)
                req.read(128)
                status = req.status
            except urllib.error.HTTPError as http_exc:
                status = http_exc.code  # 404 etc = SSL ok, só URL errada
            results[label] = {"ok": True, "ms": round((time.monotonic() - t) * 1000), "status": status}
        except Exception as exc:
            results[label] = {"ok": False, "ms": round((time.monotonic() - t) * 1000), "error": str(exc)[:200]}

    # 3. SQLAlchemy pool (conexão já estabelecida pelo pool)
    try:
        from backend.db.session import SessionLocal
        t = time.monotonic()
        with SessionLocal() as db:
            db.execute(__import__("sqlalchemy").text("SELECT 1"))
        results["sqlalchemy_pool"] = {"ok": True, "ms": round((time.monotonic() - t) * 1000)}
    except Exception as exc:
        results["sqlalchemy_pool"] = {"ok": False, "error": str(exc)[:200]}

    all_ok = all(v.get("ok") for v in results.values())
    return jsonify({"ok": all_ok, "checks": results})


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

