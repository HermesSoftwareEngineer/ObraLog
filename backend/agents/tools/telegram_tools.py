from __future__ import annotations

import concurrent.futures
import logging

from langchain_core.tools import tool
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from backend.services.telegram_client import bot_client
from backend.services.telegram_interactions import register_poll_context


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


logger = logging.getLogger("obralog.agent.telegram_tools")


def get_telegram_tools(
    *,
    chat_id: str | None,
    thread_id: str | None,
    telegram_message_thread_id: int | None,
    actor_user_id: int | None,
    actor_level: str | None,
    conversa_id: int | None = None,
) -> list:
    logger.info("[TELEGRAM_TOOLS] get_telegram_tools: iniciando chat_id=%s", chat_id)
    if not chat_id:
        logger.info("[TELEGRAM_TOOLS] get_telegram_tools: sem chat_id, retornando vazio")
        return []

    @tool
    def enviar_botoes_resposta_rapida(
        pergunta: str,
        opcoes: list[str],
        manter_teclado_visivel: bool = True,
        placeholder: str | None = None,
    ) -> dict:
        """Envia botões de resposta rápida no Telegram para coletar informação pontual."""
        question = " ".join((pergunta or "").strip().split())
        if not question:
            raise ValueError("Campo obrigatório: pergunta.")

        options = _sanitize_options(opcoes)
        keyboard = [[opt] for opt in options]

        kwargs: dict = {}
        if telegram_message_thread_id is not None:
            kwargs["message_thread_id"] = int(telegram_message_thread_id)
        if placeholder:
            value = " ".join(placeholder.strip().split())
            if value:
                kwargs["input_field_placeholder"] = value[:64]

        try:
            reply_markup = ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True,
                one_time_keyboard=not bool(manter_teclado_visivel),
            )
            msg = bot_client.submit(
                bot_client.bot.send_message(
                    chat_id=chat_id,
                    text=question,
                    reply_markup=reply_markup,
                    **kwargs,
                ),
                timeout=15,
            )
            return {
                "ok": True,
                "message": "Botões de resposta rápida enviados com sucesso.",
                "telegram_ui_dispatched": True,
                "telegram_ui_type": "reply_keyboard",
                "question": question,
                "options": options,
                "telegram_message_id": msg.message_id,
                "keep_keyboard_visible": bool(manter_teclado_visivel),
            }
        except (TimeoutError, concurrent.futures.TimeoutError):
            raise
        except Exception:
            inline_keyboard = [
                [InlineKeyboardButton(text=item, callback_data=f"rk:{idx}")]
                for idx, item in enumerate(options)
            ]
            msg = bot_client.submit(
                bot_client.bot.send_message(
                    chat_id=chat_id,
                    text=question,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard),
                    **{k: v for k, v in kwargs.items() if k == "message_thread_id"},
                ),
                timeout=15,
            )
            return {
                "ok": True,
                "message": "Reply keyboard indisponível neste contexto; inline keyboard enviado como fallback.",
                "telegram_ui_dispatched": True,
                "telegram_ui_type": "inline_keyboard_fallback",
                "question": question,
                "options": options,
                "telegram_message_id": msg.message_id,
                "keep_keyboard_visible": bool(manter_teclado_visivel),
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

        kwargs: dict = {}
        if telegram_message_thread_id is not None:
            kwargs["message_thread_id"] = int(telegram_message_thread_id)

        msg = bot_client.submit(
            bot_client.bot.send_poll(
                chat_id=chat_id,
                question=question,
                options=options,
                is_anonymous=bool(anonima),
                allows_multiple_answers=bool(multipla_escolha),
                **kwargs,
            ),
            timeout=15,
        )

        poll_id = msg.poll.id if msg.poll else None
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
            "telegram_message_id": msg.message_id,
            "multipla_escolha": bool(multipla_escolha),
            "anonima": bool(anonima),
        }

    @tool
    def encerrar_conversa_operacional() -> dict:
        """Encerra a conversa atual a pedido do usuário. Use quando o usuário pedir explicitamente para encerrar, finalizar ou fechar a conversa."""
        if actor_user_id is None:
            return {"ok": False, "message": "Contexto de usuário não identificado para encerrar a conversa."}
        try:
            from backend.db.session import SessionLocal
            from backend.agents.session_service import encerrar_conversa
            from backend.db.models import Conversa
            with SessionLocal() as db:
                target_id = conversa_id
                if target_id is None:
                    conv = (
                        db.query(Conversa)
                        .filter(
                            Conversa.usuario_id == actor_user_id,
                            Conversa.encerrada_em.is_(None),
                        )
                        .order_by(Conversa.iniciada_em.desc())
                        .first()
                    )
                    if not conv:
                        return {"ok": False, "message": "Nenhuma conversa ativa encontrada para encerrar."}
                    target_id = conv.id
                encerrar_conversa(db, target_id)
            return {"ok": True, "message": "Conversa encerrada com sucesso. Até logo!"}
        except Exception as exc:
            return {"ok": False, "message": f"Erro ao encerrar conversa: {exc}"}

    @tool
    def enviar_diario_telegram(
        diario_id: str | None = None,
        obra_nome: str | None = None,
        data: str | None = None,
        versao: int = 1,
        formato: str = "pdf",
        legenda: str | None = None,
    ) -> dict:
        """Envia o diário de obra para o usuário no Telegram como arquivo (PDF, Word ou Excel).
        Prefira passar obra_nome + data em vez de diario_id — a tool busca o diário automaticamente.
        Se diario_id não for informado ou for inválido, busca pelo diário mais recente da obra na data.
        formato aceito: 'pdf', 'word' ou 'excel'."""
        import re
        import unicodedata
        import httpx
        from backend.db.session import SessionLocal
        from backend.db.models import DiarioVersao, Diario, Obra

        fmt = (formato or "pdf").strip().lower()
        if fmt not in {"pdf", "word", "excel"}:
            return {"ok": False, "message": f"Formato inválido: '{formato}'. Use pdf, word ou excel."}

        def _norm(s: str) -> str:
            return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()

        def _is_valid_uuid(v: str) -> bool:
            return bool(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", (v or "").strip().lower()))

        resolved_diario_id = diario_id if _is_valid_uuid(diario_id or "") else None
        if resolved_diario_id is None:
            try:
                from backend.agents.tools.gateway_tools import parse_iso_date
                with SessionLocal() as db:
                    query = db.query(Diario)
                    if obra_nome:
                        obra = (
                            db.query(Obra)
                            .filter(Obra.nome.ilike(f"%{obra_nome.strip()}%"))
                            .first()
                        )
                        if obra:
                            query = query.filter(Diario.obra_id == obra.id)
                    if data:
                        try:
                            data_ref = parse_iso_date(data, "data").date() if hasattr(parse_iso_date(data, "data"), "date") else parse_iso_date(data, "data")
                        except Exception:
                            data_ref = None
                        if data_ref:
                            query = query.filter(Diario.data_inicio <= data_ref, Diario.data_fim >= data_ref)
                    diario_obj = query.order_by(Diario.created_at.desc()).first()
                    if not diario_obj:
                        return {"ok": False, "message": "Diário não encontrado. Verifique obra e data informadas."}
                    resolved_diario_id = str(diario_obj.id)
            except Exception as exc:
                return {"ok": False, "message": f"Erro ao localizar diário: {exc}"}

        try:
            if fmt == "pdf":
                with SessionLocal() as db:
                    versao_obj = (
                        db.query(DiarioVersao)
                        .filter(DiarioVersao.diario_id == resolved_diario_id, DiarioVersao.versao == versao)
                        .first()
                    )
                    if not versao_obj:
                        return {"ok": False, "message": f"Versão {versao} do diário não encontrada."}
                    storage_url = versao_obj.storage_url
                    storage_path = versao_obj.storage_path

                if storage_url:
                    with httpx.Client(timeout=60) as client:
                        r = client.get(storage_url)
                        r.raise_for_status()
                        file_bytes = r.content
                else:
                    from backend.utils.storage import get_local_pdf_path
                    local_path = get_local_pdf_path(storage_path)
                    if local_path is None or not local_path.exists():
                        return {"ok": False, "message": "PDF não encontrado no storage."}
                    file_bytes = local_path.read_bytes()

                content_type = "application/pdf"
                ext = "pdf"

            else:
                from backend.services.diario_service import get_dados_para_exportar
                with SessionLocal() as db:
                    versao_obj = (
                        db.query(DiarioVersao)
                        .filter(DiarioVersao.diario_id == resolved_diario_id, DiarioVersao.versao == versao)
                        .first()
                    )
                    if not versao_obj:
                        return {"ok": False, "message": f"Versão {versao} do diário não encontrada."}
                    tenant_id_local = versao_obj.tenant_id

                diario_info, registros_rows, frentes_schemas = get_dados_para_exportar(
                    resolved_diario_id, versao, tenant_id_local
                )

                if fmt == "word":
                    from backend.services.word_service import gerar_word_diario
                    file_bytes = gerar_word_diario(diario_info, registros_rows, frentes_schemas)
                    content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    ext = "docx"
                else:
                    from backend.services.excel_service import gerar_excel_diario
                    file_bytes = gerar_excel_diario(diario_info, registros_rows, frentes_schemas)
                    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    ext = "xlsx"

        except Exception as exc:
            return {"ok": False, "message": f"Erro ao gerar documento: {exc}"}

        try:
            with SessionLocal() as db:
                diario_obj = db.query(Diario).filter(Diario.id == resolved_diario_id).first()
                nome_obra = ""
                if diario_obj:
                    obra_obj = db.query(Obra).filter(Obra.id == diario_obj.obra_id).first()
                    nome_obra = (obra_obj.nome if obra_obj else "").replace(" ", "_")
                data_ref = ""
                if diario_obj and diario_obj.data_inicio:
                    data_ref = str(diario_obj.data_inicio).replace("-", "")
            filename = f"diario_{nome_obra}_{data_ref}_v{versao}.{ext}" if nome_obra else f"diario_v{versao}.{ext}"
        except Exception:
            filename = f"diario_v{versao}.{ext}"

        try:
            kwargs: dict = {}
            if telegram_message_thread_id is not None:
                kwargs["message_thread_id"] = int(telegram_message_thread_id)
            if legenda:
                kwargs["caption"] = legenda

            msg = bot_client.submit(
                bot_client.bot.send_document(
                    chat_id=chat_id,
                    document=(filename, file_bytes, content_type),
                    **kwargs,
                ),
                timeout=60,
            )
            message_id = msg.message_id if msg else None
            return {
                "ok": True,
                "telegram_ui_dispatched": True,
                "message": f"Diário enviado como {fmt.upper()} com sucesso.",
                "filename": filename,
                "telegram_message_id": message_id,
            }
        except Exception as exc:
            return {"ok": False, "message": f"Erro ao enviar pelo Telegram: {exc}"}

    logger.info("[TELEGRAM_TOOLS] get_telegram_tools: ok, retornando 4 tools chat_id=%s", chat_id)
    return [enviar_botoes_resposta_rapida, enviar_enquete_checklist, encerrar_conversa_operacional, enviar_diario_telegram]
