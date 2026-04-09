import hmac
import os
import logging

from flask import Blueprint, jsonify, request

try:
	from backend.services.telegram import handle_telegram_update
except ImportError:
	from services.telegram import handle_telegram_update


telegram_blueprint = Blueprint("telegram", __name__)
logger = logging.getLogger(__name__)


@telegram_blueprint.post("/telegram/webhook")
def telegram_webhook():
	print("[WEBHOOK] Nova requisição recebida!", flush=True)
	logger.info("[WEBHOOK] Nova requisição recebida")
	
	expected_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET_TOKEN")
	if expected_secret:
		received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
		if not hmac.compare_digest(received_secret, expected_secret):
			print("[WEBHOOK] Token inválido!", flush=True)
			logger.warning("[WEBHOOK] Token inválido")
			return jsonify({"ok": False, "error": "Webhook token inválido."}), 403

	payload = request.get_json(silent=True) or {}
	print(f"[WEBHOOK] Payload recebido: update_id={payload.get('update_id')}", flush=True)
	logger.info(f"[WEBHOOK] Payload recebido: update_id={payload.get('update_id')}")
	
	try:
		result = handle_telegram_update(payload)
		print(f"[WEBHOOK] Resultado: {result}", flush=True)
		logger.info(f"[WEBHOOK] Resultado: {result}")
		return jsonify(result)
	except RuntimeError as exc:
		print(f"[WEBHOOK] ERRO ao processar: {exc}", flush=True)
		logger.error(f"[WEBHOOK] ERRO ao processar: {exc}", exc_info=True)
		return jsonify({"ok": False, "error": str(exc)}), 500
	except Exception as exc:
		print(f"[WEBHOOK] ERRO inesperado: {exc}", flush=True)
		logger.error(f"[WEBHOOK] ERRO inesperado: {exc}", exc_info=True)
		return jsonify({"ok": False, "error": "Internal server error"}), 500
