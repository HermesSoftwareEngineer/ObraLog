from __future__ import annotations

from pathlib import Path
import re
import unicodedata

from backend.agents.instructions_store import read_agent_instructions
from backend.db.repository import Repository
from backend.db.session import SessionLocal


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(normalized.strip().lower().split())


class BusinessRAGService:
    """Dedicated business RAG over operational knowledge for field language."""

    def __init__(self, knowledge_path: Path | None = None):
        default_path = Path(__file__).resolve().parents[1] / "context" / "padroes_operacionais_encarregado.md"
        self.knowledge_path = knowledge_path or default_path

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

    def sugerir_campos_faltantes(self, tipo_registro: str, dados_parciais: dict) -> dict:
        checklist = self._checklist_by_type(tipo_registro)
        if not checklist:
            return {
                "ok": False,
                "message": "tipo_registro invalido. Use: producao_diaria, alerta_operacional.",
            }

        missing = [field for field in checklist if self._is_missing(self._value_for_field(field, dados_parciais))]
        validation_issues = self._validate_references(tipo_registro, dados_parciais)
        return {
            "ok": True,
            "tipo_registro": tipo_registro,
            "obrigatorios": checklist,
            "faltantes": missing,
            "completo": len(missing) == 0,
            "validacoes": validation_issues,
            "pronto_para_consolidar": len(missing) == 0 and not validation_issues,
        }

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

    def _checklist_by_type(self, tipo_registro: str) -> list[str]:
        mapping = {
            "producao_diaria": [
                "data",
                "frente_servico",
                "estaca_inicial",
                "estaca_final",
                "tempo_manha",
                "tempo_tarde",
            ],
            "alerta_operacional": [
                "tipo_alerta",
                "descricao",
                "severidade",
                "local",
            ],
        }
        return mapping.get((tipo_registro or "").strip().lower(), [])

    def _validate_references(self, tipo_registro: str, dados_parciais: dict) -> list[dict]:
        normalized_type = (tipo_registro or "").strip().lower()
        issues: list[dict] = []

        if normalized_type == "producao_diaria":
            issues.extend(self._validate_frente_servico_reference(dados_parciais))
            issues.extend(self._validate_usuario_registrador_reference(dados_parciais))

        return issues

    def _validate_frente_servico_reference(self, dados_parciais: dict) -> list[dict]:
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

    def _validate_usuario_registrador_reference(self, dados_parciais: dict) -> list[dict]:
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

        return dados_parciais.get(field_name)
