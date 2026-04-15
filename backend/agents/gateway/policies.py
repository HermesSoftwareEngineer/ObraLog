from __future__ import annotations

from backend.db.models import NivelAcesso

from .errors import GatewayValidationError
from .errors import GatewayPermissionDenied


class GatewayPolicyService:
    """Central permission checks for gateway operations.

    This class is intentionally small in phase 1 and can be expanded
    operation-by-operation in phase 2.
    """

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
    }

    def assert_can_read(self, actor_level: str) -> None:
        if actor_level not in self.READ_LEVELS:
            raise GatewayPermissionDenied("Read access denied for current profile.")

    def assert_can_write(self, actor_level: str) -> None:
        if actor_level not in self.WRITE_LEVELS:
            raise GatewayPermissionDenied("Write access denied for current profile.")

    def assert_can_manage_others(self, actor_level: str) -> None:
        if actor_level not in self.ADMIN_OR_MANAGER:
            raise GatewayPermissionDenied("Current profile cannot execute this operation for other users.")

    def assert_owner_or_manager(self, actor_level: str, actor_user_id: int, owner_user_id: int) -> None:
        if actor_level in self.ADMIN_OR_MANAGER:
            return
        if int(actor_user_id) != int(owner_user_id):
            raise GatewayPermissionDenied("Current profile can only operate over its own data.")

    def assert_execution_intent(self, intent: str | None) -> None:
        if not intent or not str(intent).strip():
            raise GatewayValidationError("Execution intent is required for write operations.")
        normalized = str(intent).strip().lower()
        if normalized not in self.ALLOWED_EXECUTION_INTENTS:
            allowed = ", ".join(sorted(self.ALLOWED_EXECUTION_INTENTS))
            raise GatewayValidationError(
                f"Unsupported execution intent: {intent}.",
                details={"allowed_intents": allowed},
            )
