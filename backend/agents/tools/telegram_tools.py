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
    tenant_id: int | None = None,
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
        """Encerra a conversa atual. Use esta tool de forma espontânea, sem necessidade de pedido explícito, quando:
        - O usuário se despedir (ex: "tchau", "até mais", "valeu", "até amanhã", "obrigado, é isso")
        - A tarefa principal foi concluída com sucesso e o usuário confirmou satisfação ou não demonstra intenção de continuar
        - O fluxo chegou a um encerramento natural e não há pendências abertas
        Não peça confirmação ao usuário — encerre diretamente e envie uma mensagem curta de despedida antes de chamar esta tool."""
        if actor_user_id is None:
            return {"ok": False, "message": "Contexto de usuário não identificado para encerrar a conversa."}
        try:
            from backend.db.session import SessionLocal
            from backend.agents.session_service import encerrar_conversa
            from backend.agents.compactacao import compactar_conversa
            from backend.db.models import Conversa
            with SessionLocal() as db:
                target_id = conversa_id
                messages_state = None
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

                # Recupera mensagens do state para compactação
                try:
                    from backend.agents.chat_db import checkpointer
                    conv_obj = db.query(Conversa).filter(Conversa.id == target_id).first()
                    if conv_obj and conv_obj.thread_id:
                        from backend.services.telegram_processor import _scoped_thread_id
                        cfg = {"configurable": {"thread_id": _scoped_thread_id(conv_obj.thread_id)}}
                        checkpoint = checkpointer.get(cfg)
                        if checkpoint:
                            messages_state = checkpoint.get("channel_values", {}).get("messages", [])
                except Exception as _exc:
                    logger.debug("[ENCERRAR] Falha ao recuperar state para compactação: %s", _exc)

                compactar_conversa(db, target_id, messages_state, compress_state=False)
                encerrar_conversa(db, target_id)

                # Reset completo da thread LangGraph: gera novo thread_id e persiste no usuário
                import uuid as _uuid
                novo_thread_id = f"{chat_id}:{_uuid.uuid4().hex}"
                from backend.db.repository import Repository
                Repository.usuarios.atualizar(db, actor_user_id, telegram_thread_id=novo_thread_id)

            # Invalida cache do thread antigo para liberar memória e forçar rebuild
            try:
                from backend.services.telegram_processor import _scoped_thread_id, _cache_get
                from backend.services.telegram_processor import _ctx_cache, _ctx_cache_lock
                old_scoped = _scoped_thread_id(thread_id) if thread_id else None
                if old_scoped:
                    with _ctx_cache_lock:
                        _ctx_cache.pop(old_scoped, None)
            except Exception:
                pass

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

    # -----------------------------------------------------------------------
    # Tool: notificar_progresso_usuario
    # -----------------------------------------------------------------------

    @tool
    def notificar_progresso_usuario(mensagem: str) -> dict:
        """Envia uma mensagem imediata ao usuário antes de executar uma tarefa demorada.
        Use quando a operação envolver múltiplas etapas, consultas ao banco, processamento de imagens ou
        geração de documentos. Exemplos: 'Analisando os registros, um instante...',
        'Gerando o diário, aguarde...', 'Processando as imagens enviadas...'"""
        try:
            bot_client.send_message(chat_id, str(mensagem))
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "message": f"Falha ao notificar: {exc}"}

    # -----------------------------------------------------------------------
    # Tool: consultar_historico_conversas
    # -----------------------------------------------------------------------

    @tool
    def consultar_historico_conversas(query: str, limit: int = 3) -> dict:
        """Busca semânticamente em conversas anteriores deste usuário no mesmo tenant.
        Use quando o usuário perguntar sobre interações passadas, decisões anteriores,
        registros feitos em outras sessões ou qualquer histórico de conversa.
        Parâmetros:
          query: descrição do que você quer encontrar (ex: 'diário da obra X em maio')
          limit: número máximo de resultados (1-5, padrão 3)"""
        if actor_user_id is None or tenant_id is None:
            return {"ok": False, "message": "Contexto de usuário não disponível."}
        try:
            from backend.agents.llms import embeddings_model
            from backend.db.session import SessionLocal
            from sqlalchemy import text as sqlt

            k = max(1, min(int(limit), 5))
            query_embedding = embeddings_model.embed_query(str(query))
            emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

            with SessionLocal() as db:
                rows = db.execute(
                    sqlt(
                        """
                        SELECT cr.resumo, c.iniciada_em, c.encerrada_em
                        FROM conversa_resumos cr
                        JOIN conversas c ON c.id = cr.conversa_id
                        WHERE c.usuario_id = :uid
                          AND c.tenant_id  = :tid
                          AND cr.embedding IS NOT NULL
                        ORDER BY cr.embedding <=> :emb::vector
                        LIMIT :k
                        """
                    ),
                    {"uid": actor_user_id, "tid": tenant_id, "emb": emb_str, "k": k},
                ).fetchall()

            if not rows:
                return {"ok": True, "encontrado": False, "resultados": [], "message": "Nenhum histórico encontrado."}

            resultados = []
            for row in rows:
                resumo, iniciada, encerrada = row
                periodo = f"{iniciada.strftime('%d/%m/%Y %H:%M') if iniciada else '?'}"
                if encerrada:
                    periodo += f" → {encerrada.strftime('%d/%m/%Y %H:%M')}"
                resultados.append({"periodo": periodo, "resumo": resumo})

            return {"ok": True, "encontrado": True, "resultados": resultados}
        except Exception as exc:
            return {"ok": False, "message": f"Erro ao consultar histórico: {exc}"}

    # -----------------------------------------------------------------------
    # Tool: conferir_contexto_tenant
    # -----------------------------------------------------------------------

    @tool
    def conferir_contexto_tenant(tenant_id_alvo: int) -> dict:
        """Carrega o contexto completo (obras, frentes de serviço, obra padrão) de um tenant
        ao qual o usuário tem acesso. Use quando o usuário quiser operar em um tenant diferente do ativo.
        IMPORTANTE: a troca de tenant só entra em vigor a partir da PRÓXIMA mensagem do usuário.
        Após chamar esta tool, informe o usuário que o contexto foi alternado e que ele deve enviar
        uma nova mensagem para iniciar operações no novo tenant. NUNCA execute registros ou consultas
        no mesmo turno em que chamar esta tool — os resultados usariam o tenant anterior.
        Parâmetros:
          tenant_id_alvo: ID do tenant a consultar (deve constar na lista de tenants acessíveis)"""
        if actor_user_id is None:
            return {"ok": False, "message": "Contexto de usuário não disponível."}
        try:
            from backend.db.session import SessionLocal
            from backend.db.repository import Repository
            from backend.agents.context.tenant_snapshot import build_tenant_snapshot
            from backend.services.telegram_processor import _cache_set, _scoped_thread_id

            with SessionLocal() as db:
                # Verificar acesso
                if not Repository.usuario_tenants.tem_acesso(db, actor_user_id, tenant_id_alvo):
                    return {"ok": False, "message": f"Você não tem acesso ao tenant ID {tenant_id_alvo}."}

                # Resolver obra padrão do tenant para este usuário
                from backend.db.models import UsuarioObra
                obras = (
                    db.query(UsuarioObra)
                    .filter(
                        UsuarioObra.usuario_id == actor_user_id,
                        UsuarioObra.tenant_id == tenant_id_alvo,
                        UsuarioObra.ativo.is_(True),
                    )
                    .all()
                )
                obra_padrao_id = None
                if len(obras) == 1:
                    obra_padrao_id = obras[0].obra_id
                else:
                    padrao = next((o for o in obras if o.eh_padrao), None)
                    if padrao:
                        obra_padrao_id = padrao.obra_id

                snapshot = build_tenant_snapshot(db, tenant_id_alvo, obra_padrao_id, actor_level)

            # Invalidar cache da thread para forçar rebuild com novo tenant na próxima mensagem
            if thread_id:
                novo_ctx = {
                    "_prebuilt_snapshot": snapshot,
                    "_prebuilt_vector_ctx": "",
                    "_prebuilt_memories": "",
                    "tenant_id": tenant_id_alvo,
                    "obra_id_ativa": obra_padrao_id,
                }
                _cache_set(_scoped_thread_id(thread_id), novo_ctx)

            return {
                "ok": True,
                "tenant_id": tenant_id_alvo,
                "obra_id_ativa": obra_padrao_id,
                "snapshot": snapshot,
                "message": (
                    f"Contexto do tenant ID {tenant_id_alvo} carregado. "
                    f"Obra ativa: ID {obra_padrao_id}." if obra_padrao_id
                    else f"Contexto do tenant ID {tenant_id_alvo} carregado. Nenhuma obra padrão definida — pergunte ao usuário qual obra usar."
                ),
            }
        except Exception as exc:
            return {"ok": False, "message": f"Erro ao conferir contexto do tenant: {exc}"}

    logger.info("[TELEGRAM_TOOLS] get_telegram_tools: ok, retornando 7 tools chat_id=%s", chat_id)
    return [
        enviar_botoes_resposta_rapida,
        enviar_enquete_checklist,
        encerrar_conversa_operacional,
        enviar_diario_telegram,
        notificar_progresso_usuario,
        consultar_historico_conversas,
        conferir_contexto_tenant,
    ]
