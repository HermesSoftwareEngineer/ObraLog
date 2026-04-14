from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
import logging
import os
import time
from typing import Any

from .contracts import GatewayRequest, GatewayResponse, WriteOptions
from .errors import GatewayError, GatewayPermissionDenied, GatewayValidationError
from .policies import GatewayPolicyService


logger = logging.getLogger("obralog.gateway")


class GatewayService:
    """Application service for business-facing gateway operations.

    Phase 1 goal:
    - Establish structure and safety hooks.
    - Keep zero production impact until wired in response/tools layer.
    """

    def __init__(self, *, policies: GatewayPolicyService | None = None):
        self.policies = policies or GatewayPolicyService()
        self.audit_file_path = os.environ.get("GATEWAY_AUDIT_FILE", "").strip() or None

    def execute_consulta(
        self,
        request: GatewayRequest,
        handler: Callable[[GatewayRequest], dict[str, Any]],
    ) -> GatewayResponse:
        started = time.perf_counter()
        if request.meta.action_route not in {"consulta", ""}:
            raise GatewayValidationError("Invalid action route for consulta mode.")
        try:
            self.policies.assert_can_read(request.actor.actor_level)
            data = self._safe_execute(request, handler)
            response = GatewayResponse(ok=True, operation=request.meta.operation, data=data)
            self._log_gateway_call(request=request, ok=True, duration_ms=self._elapsed_ms(started), result_data=response.data)
            return response
        except Exception as exc:
            self._log_gateway_call(request=request, ok=False, duration_ms=self._elapsed_ms(started), error=str(exc))
            raise

    def execute_execucao(
        self,
        request: GatewayRequest,
        handler: Callable[[GatewayRequest], dict[str, Any]],
        *,
        intent: str,
        options: WriteOptions | None = None,
    ) -> GatewayResponse:
        started = time.perf_counter()
        if request.meta.action_route not in {"execucao", ""}:
            raise GatewayValidationError("Invalid action route for execucao mode.")
        try:
            self.policies.assert_can_write(request.actor.actor_level)
            self.policies.assert_execution_intent(intent)

            effective_options = options or WriteOptions()
            if effective_options.require_confirmation and not effective_options.confirmed:
                raise GatewayValidationError(
                    "Explicit confirmation is required before write operations.",
                    details={"operation": request.meta.operation, "intent": intent},
                )

            data = self._safe_execute(request, handler)
            response = GatewayResponse(ok=True, operation=request.meta.operation, data=data)
            self._log_gateway_call(request=request, ok=True, duration_ms=self._elapsed_ms(started), result_data=response.data)
            return response
        except Exception as exc:
            self._log_gateway_call(request=request, ok=False, duration_ms=self._elapsed_ms(started), error=str(exc))
            raise

    def execute_read(
        self,
        request: GatewayRequest,
        handler: Callable[[GatewayRequest], dict[str, Any]],
    ) -> GatewayResponse:
        return self.execute_consulta(request, handler)

    def execute_write(
        self,
        request: GatewayRequest,
        handler: Callable[[GatewayRequest], dict[str, Any]],
        options: WriteOptions | None = None,
    ) -> GatewayResponse:
        intent = request.meta.intent or "registrar_producao"
        return self.execute_execucao(request, handler, intent=intent, options=options)

    def _safe_execute(
        self,
        request: GatewayRequest,
        handler: Callable[[GatewayRequest], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return handler(request) or {}
        except GatewayError:
            raise
        except PermissionError as exc:
            raise GatewayPermissionDenied(str(exc) or "Access denied for this operation.") from exc
        except ValueError as exc:
            raise GatewayValidationError(
                message=str(exc),
                details={"operation": request.meta.operation},
            ) from exc
        except Exception as exc:
            raise GatewayError(
                code="gateway_unexpected_error",
                message=str(exc),
                status_code=500,
                details={"operation": request.meta.operation},
            ) from exc

    def _elapsed_ms(self, started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

    def _log_gateway_call(
        self,
        *,
        request: GatewayRequest,
        ok: bool,
        duration_ms: int,
        result_data: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "ok": bool(ok),
            "duration_ms": int(duration_ms),
            "route": request.meta.action_route,
            "operation": request.meta.operation,
            "business_tool": request.meta.business_tool or request.meta.operation,
            "technical_operation": request.meta.technical_operation,
            "intent": request.meta.intent,
            "actor_user_id": request.actor.actor_user_id,
            "actor_level": request.actor.actor_level,
            "source": request.meta.source,
            "request_id": request.meta.request_id,
        }

        if ok:
            if isinstance(result_data, dict):
                event["result_keys"] = sorted(list(result_data.keys()))[:20]
        else:
            event["error"] = error or "unknown_error"

        logger.info("gateway_call %s", json.dumps(event, ensure_ascii=False))
        self._persist_audit_event(event)

    def _persist_audit_event(self, event: dict[str, Any]) -> None:
        if not self.audit_file_path:
            return
        try:
            with open(self.audit_file_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("Falha ao persistir trilha de auditoria do gateway: %s", str(exc))
