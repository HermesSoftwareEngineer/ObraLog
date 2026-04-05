from flask import Blueprint, jsonify, request

try:
	from backend.services.telegram import handle_telegram_update
except ImportError:
	from services.telegram import handle_telegram_update


telegram_blueprint = Blueprint("telegram", __name__)


@telegram_blueprint.post("/telegram/webhook")
def telegram_webhook():
	payload = request.get_json(silent=True) or {}
	try:
		result = handle_telegram_update(payload)
		return jsonify(result)
	except RuntimeError as exc:
		return jsonify({"ok": False, "error": str(exc)}), 500
