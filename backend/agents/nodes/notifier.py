"""Notifier node: sends an intermediate message to the user before executing the plan."""
import logging

from langchain_core.runnables import RunnableConfig

try:
    from ..state import State
except ImportError:
    from state import State  # type: ignore

logger = logging.getLogger("obralog.agent.notifier")


def _send_direct(chat_id: str, text: str, message_thread_id=None) -> None:
    if str(chat_id).startswith("wa:"):
        phone = str(chat_id)[3:]
        try:
            from backend.services.whatsapp_client import WhatsAppClient
            WhatsAppClient().send_text_message(phone, text)
        except Exception as exc:
            logger.warning("Falha ao enviar notificação WA para %s: %s", phone, exc)
    else:
        try:
            from backend.services.telegram_client import bot_client
            bot_client.send_message(chat_id, text, message_thread_id=message_thread_id)
        except Exception as exc:
            logger.warning("Falha ao enviar notificação Telegram para %s: %s", chat_id, exc)


def notifier_node(state: State, config: RunnableConfig | None = None) -> dict:
    plan = state.get("plan") or {}
    notification = plan.get("user_notification") if isinstance(plan, dict) else None

    if not notification:
        return {}

    configurable = (config or {}).get("configurable", {})
    chat_id = configurable.get("telegram_chat_id")
    message_thread_id = configurable.get("telegram_message_thread_id")

    if chat_id:
        _send_direct(str(chat_id), notification, message_thread_id)

    return {}
