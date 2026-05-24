"""WhatsApp Cloud API webhook routes.

GET  /whatsapp/webhook   — Meta hub verification challenge (required for setup)
POST /whatsapp/webhook   — Incoming messages from Meta
POST /whatsapp/simulate  — Dev-only: inject a test message without a real phone
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os

from flask import Blueprint, jsonify, request

try:
    from backend.services.whatsapp import handle_whatsapp_update
    from backend.core.config import get_ambiente
except ImportError:
    from services.whatsapp import handle_whatsapp_update  # type: ignore[no-redef]
    from core.config import get_ambiente  # type: ignore[no-redef]

whatsapp_blueprint = Blueprint("whatsapp", __name__)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Signature validation
# ---------------------------------------------------------------------------

def _validate_signature(raw_body: bytes, signature_header: str) -> bool:
    """Verify X-Hub-Signature-256 sent by Meta on every POST."""
    app_secret = os.environ.get("WHATSAPP_APP_SECRET", "")
    if not app_secret:
        logger.warning(
            "WHATSAPP_APP_SECRET não configurado — validação de assinatura desabilitada."
        )
        return True
    if not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        app_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ---------------------------------------------------------------------------
# Hub verification (GET)
# ---------------------------------------------------------------------------

@whatsapp_blueprint.get("/whatsapp/webhook")
def whatsapp_verify():
    """Meta calls this GET once when you configure the webhook in the dashboard."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    verify_token = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
    if mode == "subscribe" and token == verify_token:
        logger.info("Webhook WhatsApp verificado com sucesso.")
        return challenge, 200

    logger.warning("Falha na verificação do webhook WhatsApp.")
    return jsonify({"error": "Verificação falhou"}), 403


# ---------------------------------------------------------------------------
# Receive messages (POST)
# ---------------------------------------------------------------------------

@whatsapp_blueprint.post("/whatsapp/webhook")
def whatsapp_webhook():
    raw_body = request.get_data()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not _validate_signature(raw_body, signature):
        logger.warning("Assinatura WhatsApp inválida.")
        return jsonify({"ok": False, "error": "Assinatura inválida"}), 403

    payload = request.get_json(silent=True) or {}
    logger.info("[WA WEBHOOK] update recebido")

    try:
        result = handle_whatsapp_update(payload)
        return jsonify(result)
    except Exception as exc:
        logger.error("[WA WEBHOOK] Erro inesperado: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# Dev simulation endpoint (POST)
# ---------------------------------------------------------------------------

@whatsapp_blueprint.post("/whatsapp/simulate")
def whatsapp_simulate():
    """
    Dev-only. Inject a test WhatsApp message without needing a real phone or ngrok.

    Body: {"from": "5511999990000", "text": "Olá", "name": "Teste"}
    """
    if get_ambiente() != "dev":
        return jsonify({"error": "Disponível apenas em ambiente dev"}), 403

    body = request.get_json(silent=True) or {}
    from_phone = (body.get("from") or "").lstrip("+") or "5511900000000"
    text = body.get("text") or "teste"
    name = body.get("name") or "Simulação"

    fake_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "SIMULATED",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "0", "phone_number_id": "0"},
                    "contacts": [{"wa_id": from_phone, "profile": {"name": name}}],
                    "messages": [{
                        "from": from_phone,
                        "id": f"sim_{from_phone}_1",
                        "timestamp": "0",
                        "type": "text",
                        "text": {"body": text},
                    }],
                },
            }],
        }],
    }

    logger.info("[WA SIMULATE] phone=%s text=%s", from_phone, text)
    try:
        result = handle_whatsapp_update(fake_payload)
        return jsonify(result)
    except Exception as exc:
        logger.error("[WA SIMULATE] Erro: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500
