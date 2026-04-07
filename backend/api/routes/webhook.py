import hmac
import os

from flask import Blueprint, jsonify, request

try:
	from backend.services.telegram import handle_telegram_update
except ImportError:
	from services.telegram import handle_telegram_update


telegram_blueprint = Blueprint("telegram", __name__)


@telegram_blueprint.post("/telegram/webhook")
def telegram_webhook():
	expected_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET_TOKEN")
	if expected_secret:
		received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
		if not hmac.compare_digest(received_secret, expected_secret):
			return jsonify({"ok": False, "error": "Webhook token inválido."}), 403

	payload = request.get_json(silent=True) or {}
	try:
		result = handle_telegram_update(payload)
		return jsonify(result)
	except RuntimeError as exc:
		return jsonify({"ok": False, "error": str(exc)}), 500
