from datetime import date
from uuid import UUID

from langchain_core.tools import tool

from backend.db.models import FrenteServico, NivelAcesso, RegistroStatus
from backend.db.repository import Repository, RegistroSchemaRepository
from backend.db.session import SessionLocal

from .common import (
    agrupar_por_data,
    assert_permission,
    build_diario_do_dia_summary,
    get_diario_do_dia,
    get_registros_por_periodo,
    parse_clima,
    parse_lado_pista,
    registro_to_dict_with_images,
    resolve_frente_servico_id,
)


def build_registros_tools(
    actor_user_id: int,
    actor_level: str,
    tenant_id: int | None = None,
) -> list:
    def _parse_registro_status(value: str | None) -> RegistroStatus | None:
        if value in (None, ""):
            return None
        raw = str(value).strip().lower()
        aliases = {
            "pendente": RegistroStatus.PENDENTE,
            "aprovado": RegistroStatus.APROVADO,
            "rejeitado": RegistroStatus.REJEITADO,
        }
        parsed = aliases.get(raw)
        if not parsed:
            raise ValueError("status invalido. Use: pendente, aprovado, rejeitado.")
        return parsed

    @tool
    def criar_registro(
        data: str | None = None,
        obra_id: int | None = None,
        estaca_inicial: float | None = None,
        estaca_final: float | None = None,
        km_inicial: float | None = None,
        km_final: float | None = None,
        local_descritivo: str | None = None,
        localizacao: dict | None = None,
        tempo_manha: str | None = None,
        tempo_tarde: str | None = None,
        observacao: str | None = None,
        frente_servico_id: int | None = None,
        frente_servico_nome: str | None = None,
        pista: str | None = None,
        lado_pista: str | None = None,
        raw_text: str | None = None,
        source_message_id: str | None = None,
        status: str | None = None,
        campos_extras_valores: dict | None = None,
        resultado: float | None = None,
    ) -> dict:
        """Cria registro no diario; permite payload parcial. Consolidado exige campos basicos preenchidos."""
        assert_permission(actor_level, "create", "registros")
        observacao_normalizada = (observacao or "").strip() or None
        parsed_data = date.fromisoformat(data) if data else None

        parsed_tempo_manha = parse_clima(tempo_manha, "tempo_manha") if tempo_manha else None
        parsed_tempo_tarde = parse_clima(tempo_tarde, "tempo_tarde") if tempo_tarde else None

        localizacao = localizacao or {}
        location_type = str(localizacao.get("tipo") or "estaca").strip().lower()
        start_value = localizacao.get("valor_inicial", estaca_inicial if estaca_inicial is not None else km_inicial)
        end_value = localizacao.get("valor_final", estaca_final if estaca_final is not None else km_final)
        detail_value = localizacao.get("detalhe_texto", local_descritivo)

        # Prioridade: resultado explícito > calculado das estacas
        if resultado is None and start_value is not None and end_value is not None:
            resultado = float(end_value) - float(start_value)

        parsed_status = _parse_registro_status(status) or RegistroStatus.PENDENTE

        with SessionLocal() as db:
            source_message_uuid = None
            if source_message_id:
                try:
                    source_message_uuid = UUID(str(source_message_id))
                except Exception as exc:
                    raise ValueError("source_message_id inválido. Use UUID válido.") from exc

            resolved_frente_id = None
            if frente_servico_id is not None or frente_servico_nome:
                resolved_frente_id = resolve_frente_servico_id(
                    db,
                    frente_servico_id=frente_servico_id,
                    frente_servico_nome=frente_servico_nome,
                    tenant_id=tenant_id,
                )

            # Deriva obra da frente quando não informada explicitamente,
            # evitando registros com obra_id=NULL que ficam invisíveis no diário.
            if obra_id is None and resolved_frente_id is not None:
                frente = db.query(FrenteServico).filter(
                    FrenteServico.id == resolved_frente_id,
                    FrenteServico.tenant_id == tenant_id,
                ).first()
                if frente and frente.obra_id:
                    obra_id = frente.obra_id

            registro_schema_id = None
            if resolved_frente_id is not None:
                frente_schema = RegistroSchemaRepository.obter_para_frente(db, resolved_frente_id, tenant_id)
                if frente_schema:
                    registro_schema_id = frente_schema.id
            if registro_schema_id is None and obra_id is not None:
                obra_schema = RegistroSchemaRepository.obter_ativo_para_obra(db, obra_id, tenant_id)
                if obra_schema:
                    registro_schema_id = obra_schema.id

            # Mescla campos extras do schema no metadata_json, igual ao padrão da rota REST
            metadata = {"tipo": location_type}
            if campos_extras_valores and isinstance(campos_extras_valores, dict):
                metadata = {**metadata, **campos_extras_valores}

            registro = Repository.registros.criar(
                db=db,
                tenant_id=tenant_id,
                data=parsed_data,
                obra_id=obra_id,
                frente_servico_id=resolved_frente_id,
                usuario_registrador_id=actor_user_id,
                estaca_inicial=float(start_value) if start_value is not None else None,
                estaca_final=float(end_value) if end_value is not None else None,
                localizacao=(str(detail_value).strip() or None) if detail_value is not None else None,
                metadata_json=metadata,
                resultado=resultado,
                tempo_manha=parsed_tempo_manha,
                tempo_tarde=parsed_tempo_tarde,
                lado_pista=parse_lado_pista(lado_pista or pista),
                observacao=observacao_normalizada,
                raw_text=(raw_text or "").strip() or None,
                source_message_id=source_message_uuid,
                status=parsed_status,
                registro_schema_id=registro_schema_id,
            )
            return registro_to_dict_with_images(db, registro)

    @tool
    def anexar_imagem_registro(
        registro_id: int,
        imagens_urls: list[str],
    ) -> dict:
        """Anexa uma ou mais imagens a um registro por URL externa. Limite: 30 imagens por registro."""
        import logging as _logging
        import urllib.request as _urllib_req

        _log = _logging.getLogger("obralog.agent.imagens")

        assert_permission(actor_level, "update", "registros")

        def _processar_uma(imagem_url: str) -> dict:
            imagem_url = (imagem_url or "").strip()
            if not imagem_url:
                return {"ok": False, "message": "URL vazia."}
            if not (imagem_url.startswith("http://") or imagem_url.startswith("https://")):
                return {"ok": False, "message": "imagens_urls deve conter URLs HTTP/HTTPS válidas."}

            # Download from the temporary Telegram URL and persist to permanent storage
            # (Supabase or local fallback) so the image remains accessible after the
            # original URL expires.
            try:
                req = _urllib_req.Request(imagem_url, headers={"User-Agent": "ObraLog/1.0"})
                with _urllib_req.urlopen(req, timeout=15) as resp:
                    img_bytes = resp.read()
                    content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
                    mime_type = content_type
                    file_size = len(img_bytes)

                # Detect real mime type from magic bytes — Telegram serves images
                # as application/octet-stream regardless of actual format.
                if img_bytes[:3] == b'\xff\xd8\xff':
                    mime_type, suffix = "image/jpeg", ".jpg"
                elif img_bytes[:8] == b'\x89PNG\r\n\x1a\n':
                    mime_type, suffix = "image/png", ".png"
                elif img_bytes[:4] == b'RIFF' and img_bytes[8:12] == b'WEBP':
                    mime_type, suffix = "image/webp", ".webp"
                else:
                    ext_map = {"image/png": "png", "image/gif": "gif", "image/webp": "webp", "image/jpeg": "jpg"}
                    suffix = f".{ext_map.get(content_type, 'jpg')}"

                from backend.utils.storage import upload_imagem_registro as _upload_storage
                storage_path = _upload_storage(
                    tenant_id=tenant_id,
                    registro_id=registro_id,
                    img_bytes=img_bytes,
                    mime_type=mime_type,
                    suffix=suffix,
                )
            except Exception as exc:
                _log.warning("Nao foi possivel armazenar imagem do agente (registro %s): %s", registro_id, exc)
                return {"ok": False, "message": f"Nao foi possivel baixar ou armazenar a imagem: {exc}"}

            with SessionLocal() as db:
                registro = Repository.registros.obter_por_id(db, registro_id, tenant_id=tenant_id)
                if not registro:
                    return {"ok": False, "message": "Registro não encontrado."}
                if actor_level == NivelAcesso.ENCARREGADO.value and registro.usuario_registrador_id != actor_user_id:
                    raise PermissionError("Encarregado só pode anexar imagem em seus próprios registros.")
                try:
                    imagem = Repository.registro_imagens.criar(
                        db,
                        registro_id=registro_id,
                        external_url=imagem_url,
                        storage_path=storage_path,
                        mime_type=mime_type,
                        file_size=file_size,
                        origem="agent",
                        tenant_id=tenant_id,
                    )
                except ValueError as exc:
                    return {"ok": False, "message": str(exc)}
                return {
                    "ok": True,
                    "imagem": {
                        "id": imagem.id,
                        "registro_id": imagem.registro_id,
                        "external_url": imagem.external_url,
                        "storage_path": imagem.storage_path,
                        "origem": imagem.origem,
                    },
                }

        resultados = []
        erros = []
        for url in imagens_urls:
            r = _processar_uma(url)
            if r.get("ok"):
                resultados.append(r.get("imagem", r))
            else:
                erros.append({"url": url, "erro": r.get("message", "erro desconhecido")})
        return {
            "ok": len(resultados) > 0,
            "anexadas": len(resultados),
            "imagens": resultados,
            **({"erros": erros} if erros else {}),
        }

    @tool
    def obter_registro(registro_id: int) -> dict:
        """Obtém um registro de produção pelo ID numérico."""
        assert_permission(actor_level, "read", "registros")
        with SessionLocal() as db:
            registro = Repository.registros.obter_por_id(db, registro_id, tenant_id=tenant_id)
            if not registro:
                return {"ok": False, "message": "Registro não encontrado."}
            if actor_level == NivelAcesso.ENCARREGADO.value and registro.usuario_registrador_id != actor_user_id:
                raise PermissionError("Encarregado só pode consultar seus próprios registros.")
            data = registro_to_dict_with_images(db, registro)
            data["registrador_nome"] = registro.usuario_registrador.nome if getattr(registro, "usuario_registrador", None) else None
            return {"ok": True, "registro": data}

    @tool
    def listar_registros(
        data: str | None = None,
        obra_id: int | None = None,
        frente_servico_id: int | None = None,
        frente_servico_nome: str | None = None,
        usuario_id: int | None = None,
    ) -> list[dict]:
        """Lista registros. Pode filtrar por nome da frente para evitar depender de ID técnico."""
        assert_permission(actor_level, "read", "registros")
        with SessionLocal() as db:
            if actor_level == NivelAcesso.ENCARREGADO.value:
                registros = Repository.registros.listar_por_usuario(db, actor_user_id, tenant_id=tenant_id)
            elif data:
                registros = Repository.registros.listar_por_data(db, date.fromisoformat(data), tenant_id=tenant_id)
            elif frente_servico_id is not None or frente_servico_nome:
                resolved_frente_id = resolve_frente_servico_id(
                    db,
                    frente_servico_id=frente_servico_id,
                    frente_servico_nome=frente_servico_nome,
                    tenant_id=tenant_id,
                )
                registros = Repository.registros.listar_por_frente(db, resolved_frente_id, tenant_id=tenant_id)
            elif obra_id is not None:
                registros = Repository.registros.listar_por_obra(db, int(obra_id), tenant_id=tenant_id)
            elif usuario_id:
                registros = Repository.registros.listar_por_usuario(db, usuario_id, tenant_id=tenant_id)
            else:
                registros = Repository.registros.listar(db, tenant_id=tenant_id)
            return [registro_to_dict_with_images(db, item) for item in registros]

    @tool
    def atualizar_registro(
        registro_id: int,
        data: str | None = None,
        obra_id: int | None = None,
        frente_servico_id: int | None = None,
        frente_servico_nome: str | None = None,
        usuario_registrador_id: int | None = None,
        estaca_inicial: float | None = None,
        estaca_final: float | None = None,
        km_inicial: float | None = None,
        km_final: float | None = None,
        local_descritivo: str | None = None,
        localizacao: dict | None = None,
        resultado: float | None = None,
        tempo_manha: str | None = None,
        tempo_tarde: str | None = None,
        pista: str | None = None,
        lado_pista: str | None = None,
        observacao: str | None = None,
        raw_text: str | None = None,
        source_message_id: str | None = None,
        status: str | None = None,
    ) -> dict:
        """Atualiza registro. Pode resolver frente por nome quando o usuário não souber o ID."""
        assert_permission(actor_level, "update", "registros")
        payload = {
            "obra_id": obra_id,
            "frente_servico_id": frente_servico_id,
            "usuario_registrador_id": usuario_registrador_id,
            "resultado": resultado,
            "tempo_manha": parse_clima(tempo_manha, "tempo_manha"),
            "tempo_tarde": parse_clima(tempo_tarde, "tempo_tarde"),
            "lado_pista": parse_lado_pista(lado_pista or pista),
            "observacao": observacao,
            "raw_text": raw_text,
            "status": _parse_registro_status(status),
        }

        localizacao = localizacao or {}
        location_type = str(localizacao.get("tipo") or "estaca").strip().lower()
        start_value = localizacao.get("valor_inicial", estaca_inicial if estaca_inicial is not None else km_inicial)
        end_value = localizacao.get("valor_final", estaca_final if estaca_final is not None else km_final)
        detail_value = localizacao.get("detalhe_texto", local_descritivo)
        payload["estaca_inicial"] = float(start_value) if start_value is not None else None
        payload["estaca_final"] = float(end_value) if end_value is not None else None
        payload["localizacao"] = (str(detail_value).strip() or None) if detail_value is not None else None
        payload["metadata_json"] = {"tipo": location_type}
        if data:
            payload["data"] = date.fromisoformat(data)

        if estaca_inicial is not None and estaca_final is not None and resultado is None:
            payload["resultado"] = estaca_final - estaca_inicial

        if source_message_id is not None:
            if source_message_id == "":
                payload["source_message_id"] = None
            else:
                try:
                    payload["source_message_id"] = UUID(str(source_message_id))
                except Exception as exc:
                    raise ValueError("source_message_id inválido. Use UUID válido.") from exc

        with SessionLocal() as db:
            if frente_servico_id is not None or frente_servico_nome:
                payload["frente_servico_id"] = resolve_frente_servico_id(
                    db,
                    frente_servico_id=frente_servico_id,
                    frente_servico_nome=frente_servico_nome,
                    tenant_id=tenant_id,
                )

            registro = Repository.registros.obter_por_id(db, registro_id, tenant_id=tenant_id)
            if not registro:
                return {"ok": False, "message": "Registro não encontrado."}
            if actor_level == NivelAcesso.ENCARREGADO.value and registro.usuario_registrador_id != actor_user_id:
                raise PermissionError("Encarregado só pode atualizar seus próprios registros.")
            updated = Repository.registros.atualizar(db, registro_id, tenant_id=tenant_id, **payload)
            return {"ok": True, "registro": registro_to_dict_with_images(db, updated)}

    @tool
    def atualizar_status_registro(registro_id: int, status: str) -> dict:
        """Atualiza apenas o status do registro; aprovado exige campos basicos preenchidos."""
        assert_permission(actor_level, "update", "registros")
        parsed_status = _parse_registro_status(status)
        if parsed_status is None:
            raise ValueError("status invalido. Use: pendente, aprovado, rejeitado.")

        with SessionLocal() as db:
            registro = Repository.registros.obter_por_id(db, registro_id, tenant_id=tenant_id)
            if not registro:
                return {"ok": False, "message": "Registro não encontrado."}
            if actor_level == NivelAcesso.ENCARREGADO.value and registro.usuario_registrador_id != actor_user_id:
                raise PermissionError("Encarregado só pode atualizar seus próprios registros.")

            updated = Repository.registros.atualizar_status(db, registro_id, parsed_status, tenant_id=tenant_id)
            return {"ok": True, "registro": registro_to_dict_with_images(db, updated)}

    @tool
    def deletar_registro(registro_id: int) -> dict:
        """Deleta registro do diário."""
        assert_permission(actor_level, "delete", "registros")
        with SessionLocal() as db:
            registro = Repository.registros.obter_por_id(db, registro_id, tenant_id=tenant_id)
            if not registro:
                return {"ok": False, "message": "Registro não encontrado."}
            if actor_level == NivelAcesso.ENCARREGADO.value and registro.usuario_registrador_id != actor_user_id:
                raise PermissionError("Encarregado só pode deletar seus próprios registros.")
            ok = Repository.registros.deletar(db, registro_id, tenant_id=tenant_id)
            return {"ok": ok}

    @tool
    def consultar_diario_dia(data: str, frente_servico_id: int | None = None) -> dict:
        """Consulta diário consolidado de um dia, com totais de registros, resultado e clima."""
        assert_permission(actor_level, "read", "registros")
        data_alvo = date.fromisoformat(data)
        with SessionLocal() as db:
            registros = get_diario_do_dia(db, data=data_alvo, frente_servico_id=frente_servico_id, tenant_id=tenant_id)
            if actor_level == NivelAcesso.ENCARREGADO.value:
                registros = [r for r in registros if r.usuario_registrador_id == actor_user_id]

        if not registros:
            return {"ok": False, "message": "Nenhum registro encontrado para os filtros informados."}

        return {"ok": True, "diario": build_diario_do_dia_summary(data_alvo, registros)}

    @tool
    def consultar_diario_periodo(
        data_inicio: str,
        data_fim: str,
        frente_servico_id: int | None = None,
        usuario_id: int | None = None,
        apenas_impraticaveis: bool = False,
    ) -> dict:
        """Consulta diário por período, agrupado por dia, com totais gerais."""
        assert_permission(actor_level, "read", "registros")
        inicio = date.fromisoformat(data_inicio)
        fim = date.fromisoformat(data_fim)
        if fim < inicio:
            raise ValueError("data_fim não pode ser anterior a data_inicio.")
        if (fim - inicio).days > 365:
            raise ValueError("Período máximo permitido é de 365 dias.")

        with SessionLocal() as db:
            effective_usuario = actor_user_id if actor_level == NivelAcesso.ENCARREGADO.value else usuario_id
            registros = get_registros_por_periodo(
                db,
                data_inicio=inicio,
                data_fim=fim,
                frente_servico_id=frente_servico_id,
                usuario_id=effective_usuario,
                apenas_impraticaveis=apenas_impraticaveis,
                tenant_id=tenant_id,
            )

        grouped = agrupar_por_data(registros)
        dias = [build_diario_do_dia_summary(day, items) for day, items in grouped.items()]
        total_resultado = round(sum(day["total_resultado"] for day in dias), 2)
        total_dias = len(dias)
        total_dias_impraticaveis = sum(1 for day in dias if day["dias_impraticaveis"])

        return {
            "ok": True,
            "relatorio": {
                "data_inicio": inicio.isoformat(),
                "data_fim": fim.isoformat(),
                "dias": dias,
                "total_resultado_periodo": total_resultado,
                "total_dias": total_dias,
                "total_dias_impraticaveis": total_dias_impraticaveis,
                "media_diaria": round(total_resultado / total_dias, 2) if total_dias else 0.0,
            },
        }

    return [
        criar_registro,
        anexar_imagem_registro,
        obter_registro,
        listar_registros,
        atualizar_registro,
        atualizar_status_registro,
        deletar_registro,
        consultar_diario_dia,
        consultar_diario_periodo,
    ]
