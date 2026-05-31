"""
Regras de permissão e validação de intenção do gateway.

GatewayPolicyService é a única fonte da verdade para:
- Quais níveis de acesso podem ler e escrever
- Quais intenções de execução são válidas
- Como normalizar uma intenção recebida do agente (aliases → canônico)
"""
from __future__ import annotations

from backend.db.models import NivelAcesso

from .errors import GatewayPermissionDenied, GatewayValidationError


# Aliases aceitos pelo agente mapeados para a intenção canônica.
# Centralizado aqui para evitar duplicação com gateway_tools.
_INTENT_ALIASES: dict[str, str] = {
    "criar_parcial": "registrar_producao",
    "criar_registro_parcial": "registrar_producao",
    "criar_registro": "registrar_producao",
    "abrir_registro": "registrar_producao",
    "registrar_parcial": "registrar_producao",
    "atualizar_parcial": "atualizar_registro",
    "anexar_imagem": "atualizar_registro",
    "anexar_foto": "atualizar_registro",
    "vincular_imagem": "atualizar_registro",
    "criar_frente": "gerenciar_frente_servico",
    "cadastrar_frente": "gerenciar_frente_servico",
    "atualizar_frente": "gerenciar_frente_servico",
    "editar_frente": "gerenciar_frente_servico",
    "deletar_frente": "gerenciar_frente_servico",
    "remover_frente": "gerenciar_frente_servico",
    "cadastrar_tipo_alerta": "gerenciar_tipo_alerta",
    "criar_tipo_alerta": "gerenciar_tipo_alerta",
    "atualizar_tipo_alerta": "gerenciar_tipo_alerta",
    "deletar_tipo_alerta": "gerenciar_tipo_alerta",
    "remover_tipo_alerta": "gerenciar_tipo_alerta",
    "consolidar": "consolidar_registro",
    "gerar_diario_obra": "gerar_diario",
    "criar_diario": "gerar_diario",
    "regerar_diario": "gerar_diario",
    "diario_obra": "gerar_diario",
}


class GatewayPolicyService:
    READ_LEVELS = {
        NivelAcesso.ADMINISTRADOR.value,
        NivelAcesso.GERENTE.value,
        NivelAcesso.ENCARREGADO.value,
    }

    WRITE_LEVELS = {
        NivelAcesso.ADMINISTRADOR.value,
        NivelAcesso.GERENTE.value,
        NivelAcesso.ENCARREGADO.value,
    }

    ADMIN_OR_MANAGER = {
        NivelAcesso.ADMINISTRADOR.value,
        NivelAcesso.GERENTE.value,
    }

    ALLOWED_EXECUTION_INTENTS = {
        "registrar_producao",
        "registrar_alerta",
        "atualizar_registro",
        "consolidar_registro",
        "gerenciar_frente_servico",
        "gerenciar_tipo_alerta",
        "gerar_diario",
    }

    @classmethod
    def normalize_intent(cls, intent: str | None, *, default: str) -> str:
        """Normaliza intenção do agente para um valor canônico, aplicando aliases conhecidos.

        Retorna o default se a intenção for nula, vazia ou não reconhecida.
        """
        if not intent or not str(intent).strip():
            return default
        normalized = str(intent).strip().lower()
        normalized = _INTENT_ALIASES.get(normalized, normalized)
        if normalized in cls.ALLOWED_EXECUTION_INTENTS:
            return normalized
        return default

    def assert_can_read(self, actor_level: str) -> None:
        if actor_level not in self.READ_LEVELS:
            raise GatewayPermissionDenied("Perfil sem permissão de leitura.")

    def assert_can_write(self, actor_level: str) -> None:
        if actor_level not in self.WRITE_LEVELS:
            raise GatewayPermissionDenied("Perfil sem permissão de escrita.")

    def assert_can_manage_others(self, actor_level: str) -> None:
        if actor_level not in self.ADMIN_OR_MANAGER:
            raise GatewayPermissionDenied("Perfil não pode executar esta operação por outros usuários.")

    def assert_owner_or_manager(self, actor_level: str, actor_user_id: int, owner_user_id: int) -> None:
        if actor_level in self.ADMIN_OR_MANAGER:
            return
        if int(actor_user_id) != int(owner_user_id):
            raise GatewayPermissionDenied("Perfil só pode operar sobre seus próprios dados.")

    def assert_execution_intent(self, intent: str | None) -> None:
        """Valida que a intenção está entre as permitidas para operações de escrita."""
        if not intent or not str(intent).strip():
            raise GatewayValidationError("Intenção de execução é obrigatória para operações de escrita.")
        normalized = str(intent).strip().lower()
        if normalized not in self.ALLOWED_EXECUTION_INTENTS:
            allowed = ", ".join(sorted(self.ALLOWED_EXECUTION_INTENTS))
            raise GatewayValidationError(
                f"Intenção de execução inválida: {intent}.",
                details={"intencoes_validas": allowed},
            )
