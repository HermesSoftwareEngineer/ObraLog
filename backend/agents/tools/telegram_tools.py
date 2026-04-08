from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

from langchain_core.tools import tool

from backend.services.telegram_interactions import register_poll_context


def _telegram_api_call(method: str, params: dict) -> dict:
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN não configurado.")

    url = f"https://api.telegram.org/bot{token}/{method}"
    payload = json.dumps(params).encode("utf-8")
    request = Request(url, data=payload, headers={"Content-Type": "application/json"})

    with urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))

    if not data.get("ok"):
        description = data.get("description") or "Erro ao chamar API do Telegram."
        raise RuntimeError(description)
    return data


def _sanitize_options(options: list[str], *, minimum: int = 2, maximum: int = 10) -> list[str]:
    cleaned = []
    seen = set()
    for option in options:
        value = " ".join(str(option).strip().split())
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)

    if len(cleaned) < minimum:
        raise ValueError(f"Você precisa informar pelo menos {minimum} opções válidas.")
    if len(cleaned) > maximum:
        raise ValueError(f"Você pode informar no máximo {maximum} opções.")
    return cleaned


def get_telegram_tools(
    *,
    chat_id: str | None,
    thread_id: str | None,
    telegram_message_thread_id: int | None,
    actor_user_id: int | None,
    actor_level: str | None,
) -> list:
    if not chat_id:
        return []

    @tool
    def enviar_botoes_resposta_rapida(
        pergunta: str,
        opcoes: list[str],
        manter_teclado_visivel: bool = False,
        placeholder: str | None = None,
    ) -> dict:
        """Envia botões de resposta rápida no Telegram para coletar informação pontual."""
        question = " ".join((pergunta or "").strip().split())
        if not question:
            raise ValueError("Campo obrigatório: pergunta.")

        options = _sanitize_options(opcoes)
        keyboard = [[{"text": item}] for item in options]
        reply_markup = {
            "keyboard": keyboard,
            "resize_keyboard": True,
            "one_time_keyboard": not manter_teclado_visivel,
            "selective": False,
        }
        if placeholder:
            value = " ".join(placeholder.strip().split())
            if value:
                reply_markup["input_field_placeholder"] = value[:64]

        payload = {
            "chat_id": chat_id,
            "text": question,
            "reply_markup": reply_markup,
        }
        if telegram_message_thread_id is not None:
            payload["message_thread_id"] = int(telegram_message_thread_id)

        result = _telegram_api_call("sendMessage", payload)
        message_id = ((result.get("result") or {}).get("message_id"))
        return {
            "ok": True,
            "message": "Botões de resposta rápida enviados com sucesso.",
            "telegram_ui_dispatched": True,
            "telegram_ui_type": "reply_keyboard",
            "question": question,
            "options": options,
            "telegram_message_id": message_id,
        }

    @tool
    def enviar_enquete_checklist(
        pergunta: str,
        itens_checklist: list[str],
        multipla_escolha: bool = True,
        anonima: bool = False,
    ) -> dict:
        """Envia enquete de checklist no Telegram para coletar status de itens objetivos."""
        question = " ".join((pergunta or "").strip().split())
        if not question:
            raise ValueError("Campo obrigatório: pergunta.")

        options = _sanitize_options(itens_checklist)
        payload = {
            "chat_id": chat_id,
            "question": question,
            "options": options,
            "is_anonymous": bool(anonima),
            "allows_multiple_answers": bool(multipla_escolha),
        }
        if telegram_message_thread_id is not None:
            payload["message_thread_id"] = int(telegram_message_thread_id)

        result = _telegram_api_call("sendPoll", payload)

        result_payload = result.get("result") or {}
        poll_payload = result_payload.get("poll") or {}
        poll_id = poll_payload.get("id")
        if poll_id and thread_id and actor_user_id is not None and actor_level:
            register_poll_context(
                poll_id,
                chat_id=str(chat_id),
                thread_id=str(thread_id),
                telegram_message_thread_id=telegram_message_thread_id,
                actor_user_id=int(actor_user_id),
                actor_level=str(actor_level),
                question=question,
                options=options,
            )

        return {
            "ok": True,
            "message": "Enquete de checklist enviada com sucesso.",
            "telegram_ui_dispatched": True,
            "telegram_ui_type": "poll",
            "question": question,
            "options": options,
            "poll_id": poll_id,
            "telegram_message_id": result_payload.get("message_id"),
            "multipla_escolha": bool(multipla_escolha),
            "anonima": bool(anonima),
        }

    return [enviar_botoes_resposta_rapida, enviar_enquete_checklist]