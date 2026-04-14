from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .contracts import GatewayRequest, GatewayResponse, WriteOptions
from .gateway_service import GatewayService


class GatewayActionRouter:
    """Explicit action routes for predictable gateway behavior.

    - consulta: read-only route
    - execucao: write route with intent + confirmation enforcement
    """

    def __init__(self, service: GatewayService | None = None):
        self.service = service or GatewayService()

    def consulta(
        self,
        request: GatewayRequest,
        handler: Callable[[GatewayRequest], dict[str, Any]],
    ) -> GatewayResponse:
        return self.service.execute_consulta(request, handler)

    def execucao(
        self,
        request: GatewayRequest,
        handler: Callable[[GatewayRequest], dict[str, Any]],
        *,
        intent: str,
        confirmed: bool,
    ) -> GatewayResponse:
        return self.service.execute_execucao(
            request,
            handler,
            intent=intent,
            options=WriteOptions(require_confirmation=True, confirmed=bool(confirmed)),
        )

    def execucao_sem_confirmacao(
        self,
        request: GatewayRequest,
        handler: Callable[[GatewayRequest], dict[str, Any]],
        *,
        intent: str,
    ) -> GatewayResponse:
        return self.service.execute_execucao(
            request,
            handler,
            intent=intent,
            options=WriteOptions(require_confirmation=False, confirmed=True),
        )
