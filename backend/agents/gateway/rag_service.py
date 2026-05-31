from __future__ import annotations

from pathlib import Path
import re
import unicodedata

from backend.agents.instructions_store import read_agent_instructions
from backend.agents.gateway.location_profile import build_location_profile
from backend.db.models import FrenteServico, RegistroSchema
from backend.db.repository import Repository, RegistroRepository, RegistroSchemaRepository
from backend.db.session import SessionLocal


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(normalized.strip().lower().split())


class BusinessRAGService:
    """Dedicated business RAG over operational knowledge for field language."""

    def __init__(self, knowledge_path: Path | None = None):
        default_path = Path(__file__).resolve().parents[1] / "context" / "padroes_operacionais_encarregado.md"
        self.knowledge_path = knowledge_path or default_path

    def consultar_schema_frente(self, frente_servico: str, tenant_id: int | None = None) -> dict:
        """Retorna campos obrigatórios e extras do RegistroSchema da frente de serviço."""
        dados = {"frente_servico": frente_servico}
        schema = self._fetch_schema_for_frente(dados, tenant_id=tenant_id)
        if schema is None:
            return {
                "ok": True,
                "frente_servico": frente_servico,
                "schema_configurado": False,
                "campos_obrigatorios": [],
                "campos_localizacao": [],
                "campos_extras": [],
                "message": "Frente nao possui schema configurado. Use os campos padrao de producao_diaria.",
            }

        # Filtra False por compatibilidade com registros antigos gravados antes da sanitização na API.
        campos_ativos = {c: v for c, v in (getattr(schema, "campos_ativos", None) or {}).items() if v}
        recognized = RegistroRepository._SCHEMA_CAMPO_TO_ATTR
        _location_campos = {"localizacao", "estaca_inicial", "estaca_final"}

        obrigatorios = [c for c in campos_ativos if c in recognized and c not in _location_campos]
        campos_localizacao = [c for c in campos_ativos if c in _location_campos]
        extras = self._schema_campos_extras(schema)

        return {
            "ok": True,
            "frente_servico": frente_servico,
            "schema_configurado": True,
            "schema_nome": getattr(schema, "nome", None),
            "campos_obrigatorios": obrigatorios,
            "campos_localizacao": campos_localizacao,
            "campos_extras": extras,
        }

    def consultar_padroes_operacionais(self, pergunta: str, k: int = 3) -> dict:
        blocks = self._load_blocks()
        if not blocks:
            return {
                "ok": True,
                "pergunta": pergunta,
                "itens": [],
                "encontrado": False,
                "message": "Base de conhecimento operacional indisponivel no momento.",
            }

        query_tokens = self._tokens(pergunta)
        scored: list[tuple[int, str]] = []
        for block in blocks:
            block_tokens = self._tokens(block)
            score = len(query_tokens.intersection(block_tokens))
            scored.append((score, block))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [item[1] for item in scored[: max(1, min(int(k), 8))] if item[0] > 0]
        if not selected:
            selected = blocks[:1]

        return {
            "ok": True,
            "pergunta": pergunta,
            "itens": selected,
            "encontrado": bool(selected),
        }

    def sugerir_campos_faltantes(
        self,
        tipo_registro: str,
        dados_parciais: dict,
        tenant_id: int | None = None,
        obra_id_ativa: int | None = None,
        location_profile: str | None = None,
    ) -> dict:
        effective_location_mode = self._resolve_location_mode(dados_parciais, location_profile=location_profile)

        schema = None
        if (tipo_registro or "").strip().lower() == "producao_diaria":
            schema = self._fetch_schema_for_frente(dados_parciais, tenant_id=tenant_id)

        checklist = self._checklist_by_type(
            tipo_registro,
            dados_parciais,
            location_profile=effective_location_mode,
            schema=schema,
        )
        if not checklist:
            return {
                "ok": False,
                "message": "tipo_registro invalido. Use: producao_diaria, alerta_operacional.",
            }

        missing = [field for field in checklist if self._is_missing(self._value_for_field(field, dados_parciais))]
        validation_issues = self._validate_references(tipo_registro, dados_parciais, tenant_id=tenant_id)
        profile = build_location_profile(effective_location_mode)

        campos_extras_info = self._schema_campos_extras(schema) if schema else []

        return {
            "ok": True,
            "tipo_registro": tipo_registro,
            "tenant_id": tenant_id,
            "obra_id_ativa": obra_id_ativa,
            "perfil_localizacao": profile.mode,
            "labels_localizacao": profile.labels,
            "obrigatorios": checklist,
            "faltantes": missing,
            "campos_extras": campos_extras_info,
            "completo": len(missing) == 0,
            "validacoes": validation_issues,
            "pronto_para_consolidar": len(missing) == 0 and not validation_issues,
        }

    def _resolve_location_mode(self, dados_parciais: dict, location_profile: str | None = None) -> str:
        inferred_type = self._value_for_field("tipo_localizacao", dados_parciais)
        if isinstance(inferred_type, str) and inferred_type.strip():
            return inferred_type.strip().lower()
        return build_location_profile(location_profile).mode

    def _load_blocks(self) -> list[str]:
        blocks: list[str] = []

        if self.knowledge_path.exists():
            content = self.knowledge_path.read_text(encoding="utf-8")
            chunks = re.split(r"\n## ", content)
            for idx, chunk in enumerate(chunks):
                chunk = chunk.strip()
                if not chunk:
                    continue
                if idx > 0:
                    chunk = "## " + chunk
                blocks.append(chunk)

        user_instructions = read_agent_instructions().strip()
        if user_instructions:
            blocks.append(
                "## Instrucoes Operacionais Editaveis do Usuario\n"
                f"{user_instructions}"
            )

        return blocks

    def _tokens(self, text: str) -> set[str]:
        normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        parts = re.findall(r"[a-z0-9_]{3,}", normalized.lower())
        return set(parts)

    def _checklist_by_type(
        self,
        tipo_registro: str,
        dados_parciais: dict,
        location_profile: str | None = None,
        schema: "RegistroSchema | None" = None,
    ) -> list[str]:
        normalized_type = (tipo_registro or "").strip().lower()
        if normalized_type not in {"producao_diaria", "alerta_operacional"}:
            return []

        if normalized_type == "alerta_operacional":
            return ["tipo_alerta", "descricao", "severidade", "local"]

        # producao_diaria: localização vem do schema quando existe, do perfil do tenant quando não existe.
        # Se o schema não tem nenhum campo de localização configurado, localização não é cobrada —
        # independentemente do perfil padrão do tenant.
        _location_campos = {"localizacao", "estaca_inicial", "estaca_final"}

        if schema is not None:
            campos_ativos = {c for c, v in (getattr(schema, "campos_ativos", None) or {}).items() if v}
            schema_location = [c for c in campos_ativos if c in _location_campos]
            location_required = schema_location
        else:
            profile = build_location_profile(location_profile)
            location_type_value = self._value_for_field("tipo_localizacao", dados_parciais)
            has_location_type = not self._is_missing(location_type_value)
            location_required = profile.required_fields if has_location_type else []

        universal = ["data", "frente_servico"] + location_required

        if schema is None:
            # Sem schema: usa base conservador hardcoded
            return universal + ["tempo_manha", "tempo_tarde"]

        # Com schema: campos_ativos é a fonte de verdade para campos não-universais.
        recognized = RegistroRepository._SCHEMA_CAMPO_TO_ATTR
        schema_required = [c for c in campos_ativos if c in recognized and c not in _location_campos]

        extras_required = [
            extra["chave"] for extra in self._schema_campos_extras(schema)
            if extra.get("chave") and extra.get("obrigatorio")
        ]

        return universal + schema_required + extras_required

    def _fetch_schema_for_frente(self, dados_parciais: dict, tenant_id: int | None = None) -> "RegistroSchema | None":
        """Resolve o RegistroSchema seguindo a mesma hierarquia de criar_registro:
        1. registro_schema_id direto na frente
        2. schema ativo via obra da frente (obter_ativo_para_obra)
        """
        frente_id = dados_parciais.get("frente_servico_id")
        frente_nome = dados_parciais.get("frente_servico") or dados_parciais.get("frente_servico_nome")

        if self._is_missing(frente_id) and self._is_missing(frente_nome):
            return None

        try:
            with SessionLocal() as db:
                frente: FrenteServico | None = None

                if not self._is_missing(frente_id):
                    try:
                        frente = Repository.frentes_servico.obter_por_id(db, int(frente_id), tenant_id=tenant_id)
                    except TypeError:
                        frente = Repository.frentes_servico.obter_por_id(db, int(frente_id))
                elif isinstance(frente_nome, str) and frente_nome.strip():
                    normalized = _normalize_text(frente_nome)
                    try:
                        frentes = Repository.frentes_servico.listar(db, tenant_id=tenant_id)
                    except TypeError:
                        frentes = Repository.frentes_servico.listar(db)
                    exact = [f for f in frentes if _normalize_text(str(f.nome or "")) == normalized]
                    frente = exact[0] if len(exact) == 1 else None

                if frente is None:
                    return None

                # Prioridade 1: schema direto na frente
                if frente.registro_schema_id:
                    schema = (
                        db.query(RegistroSchema)
                        .filter(
                            RegistroSchema.id == frente.registro_schema_id,
                            RegistroSchema.tenant_id == tenant_id,
                        )
                        .first()
                    )
                    if schema:
                        return schema

                # Prioridade 2: schema ativo via obra (mesma lógica de criar_registro)
                if frente.obra_id and tenant_id is not None:
                    return RegistroSchemaRepository.obter_ativo_para_obra(db, frente.obra_id, tenant_id)

                return None
        except Exception:
            return None

    def _schema_campos_extras(self, schema: "RegistroSchema | None") -> list[dict]:
        if schema is None:
            return []
        extras = getattr(schema, "campos_extras", None)
        if not isinstance(extras, list):
            return []
        result = []
        for item in extras:
            if not isinstance(item, dict):
                continue
            key = item.get("key") or item.get("chave")
            label = item.get("label") or item.get("rotulo") or key
            tipo = item.get("type") or item.get("tipo") or "text"
            obrigatorio = bool(item.get("required") or item.get("obrigatorio"))
            options = item.get("options") or item.get("opcoes")
            entry: dict = {"chave": key, "label": label, "tipo": tipo, "obrigatorio": obrigatorio}
            if options:
                entry["opcoes"] = options
            result.append(entry)
        return result

    def _validate_references(self, tipo_registro: str, dados_parciais: dict, tenant_id: int | None = None) -> list[dict]:
        normalized_type = (tipo_registro or "").strip().lower()
        issues: list[dict] = []

        if normalized_type == "producao_diaria":
            issues.extend(self._validate_frente_servico_reference(dados_parciais, tenant_id=tenant_id))
            issues.extend(self._validate_usuario_registrador_reference(dados_parciais, tenant_id=tenant_id))

        return issues

    def _validate_frente_servico_reference(self, dados_parciais: dict, tenant_id: int | None = None) -> list[dict]:
        frente_id = dados_parciais.get("frente_servico_id")
        frente_nome = dados_parciais.get("frente_servico") or dados_parciais.get("frente_servico_nome")

        if self._is_missing(frente_id) and self._is_missing(frente_nome):
            return []

        with SessionLocal() as db:
            if frente_id not in (None, ""):
                try:
                    parsed_id = int(frente_id)
                except Exception:
                    return [
                        {
                            "campo": "frente_servico_id",
                            "status": "invalido",
                            "valor": frente_id,
                            "message": "frente_servico_id deve ser um inteiro valido.",
                        }
                    ]

                try:
                    frente = Repository.frentes_servico.obter_por_id(db, parsed_id, tenant_id=tenant_id)
                except TypeError:
                    frente = Repository.frentes_servico.obter_por_id(db, parsed_id)
                if frente:
                    return []
                return [
                    {
                        "campo": "frente_servico_id",
                        "status": "inexistente",
                        "valor": parsed_id,
                        "message": "A frente de servico informada nao existe.",
                        "next_steps": [
                            "confirmar o nome da frente com o usuario",
                            "escolher uma frente cadastrada",
                            "cadastrar a frente de servico se o perfil permitir",
                        ],
                    }
                ]

            if isinstance(frente_nome, str) and frente_nome.strip():
                normalized_name = _normalize_text(frente_nome)
                try:
                    frentes = Repository.frentes_servico.listar(db, tenant_id=tenant_id)
                except TypeError:
                    frentes = Repository.frentes_servico.listar(db)
                exact = [item for item in frentes if _normalize_text(str(item.nome or "")) == normalized_name]
                partial = [item for item in frentes if normalized_name in _normalize_text(str(item.nome or ""))]
                candidates = exact or partial
                if len(candidates) == 1:
                    return []
                if len(candidates) > 1:
                    return [
                        {
                            "campo": "frente_servico",
                            "status": "ambiguo",
                            "valor": frente_nome,
                            "message": "A frente de servico informada e ambigua.",
                            "opcoes": [str(item.nome).strip() for item in candidates[:8] if str(item.nome).strip()],
                            "next_steps": [
                                "pedir ao usuario para escolher uma das opcoes",
                                "usar o nome exato da frente",
                            ],
                        }
                    ]

                return [
                    {
                        "campo": "frente_servico",
                        "status": "inexistente",
                        "valor": frente_nome,
                        "message": "A frente de servico informada nao existe.",
                        "next_steps": [
                            "pedir ao usuario para confirmar o nome da frente",
                            "usar uma frente cadastrada",
                            "cadastrar a frente de servico se o perfil permitir",
                        ],
                    }
                ]

        return []

    def _validate_usuario_registrador_reference(self, dados_parciais: dict, tenant_id: int | None = None) -> list[dict]:
        usuario_id = dados_parciais.get("usuario_registrador_id")
        if self._is_missing(usuario_id):
            return []

        try:
            parsed_id = int(usuario_id)
        except Exception:
            return [
                {
                    "campo": "usuario_registrador_id",
                    "status": "invalido",
                    "valor": usuario_id,
                    "message": "usuario_registrador_id deve ser um inteiro valido.",
                }
            ]

        with SessionLocal() as db:
            try:
                usuario = Repository.usuarios.obter_por_id(db, parsed_id, tenant_id=tenant_id)
            except TypeError:
                usuario = Repository.usuarios.obter_por_id(db, parsed_id)
            if usuario:
                return []

        return [
            {
                "campo": "usuario_registrador_id",
                "status": "inexistente",
                "valor": parsed_id,
                "message": "O usuario registrador informado nao existe.",
                "next_steps": ["corrigir o usuario registrador", "manter o registrador atual da conversa se for o caso"],
            }
        ]

    def _is_missing(self, value: object) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        if isinstance(value, list) and not value:
            return True
        return False

    def _value_for_field(self, field_name: str, dados_parciais: dict) -> object:
        if field_name == "frente_servico":
            if not self._is_missing(dados_parciais.get("frente_servico")):
                return dados_parciais.get("frente_servico")
            if not self._is_missing(dados_parciais.get("frente_servico_id")):
                return dados_parciais.get("frente_servico_id")
            if not self._is_missing(dados_parciais.get("frente_servico_nome")):
                return dados_parciais.get("frente_servico_nome")
            return None

        if field_name == "km_inicial":
            if not self._is_missing(dados_parciais.get("km_inicial")):
                return dados_parciais.get("km_inicial")
            if not self._is_missing(dados_parciais.get("estaca_inicial")):
                return dados_parciais.get("estaca_inicial")
            if isinstance(dados_parciais.get("localizacao"), dict):
                return dados_parciais.get("localizacao", {}).get("valor_inicial")
            return None

        if field_name == "km_final":
            if not self._is_missing(dados_parciais.get("km_final")):
                return dados_parciais.get("km_final")
            if not self._is_missing(dados_parciais.get("estaca_final")):
                return dados_parciais.get("estaca_final")
            if isinstance(dados_parciais.get("localizacao"), dict):
                return dados_parciais.get("localizacao", {}).get("valor_final")
            return None

        if field_name == "local_descritivo":
            if not self._is_missing(dados_parciais.get("local_descritivo")):
                return dados_parciais.get("local_descritivo")
            loc = dados_parciais.get("localizacao")
            if isinstance(loc, dict):
                return loc.get("detalhe_texto")
            if not self._is_missing(loc):
                return loc
            return None

        if field_name == "tipo_localizacao":
            # 1. Valor explícito passado diretamente pelo agente
            direct = dados_parciais.get("tipo_localizacao")
            if isinstance(direct, str) and direct.strip():
                normalized = direct.strip().lower()
                return "texto" if normalized == "text" else normalized

            # 2. Dentro do objeto localizacao
            if isinstance(dados_parciais.get("localizacao"), dict):
                tipo = dados_parciais.get("localizacao", {}).get("tipo")
                if isinstance(tipo, str) and tipo.strip():
                    normalized = tipo.strip().lower()
                    return "texto" if normalized == "text" else normalized

            # 3. Inferir pelos campos numéricos ou descritivo
            if not self._is_missing(dados_parciais.get("km_inicial")) or not self._is_missing(dados_parciais.get("km_final")):
                return "km"

            if not self._is_missing(dados_parciais.get("estaca_inicial")) or not self._is_missing(dados_parciais.get("estaca_final")):
                return "estaca"

            if not self._is_missing(self._value_for_field("local_descritivo", dados_parciais)):
                return "texto"

            return None

        # Campos extras do schema ficam aninhados em metadata_json ou no próprio dict
        metadata = dados_parciais.get("metadata_json") or {}
        if isinstance(metadata, dict) and field_name in metadata:
            return metadata[field_name]

        return dados_parciais.get(field_name)
