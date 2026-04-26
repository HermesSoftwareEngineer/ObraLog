from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GatewayError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: dict | None = None
    next_steps: list[str] | None = None

    def to_dict(self) -> dict:
        payload = {
            "ok": False,
            "error": self.message,
            "code": self.code,
        }
        if self.details:
            payload["details"] = self.details
        if self.next_steps:
            payload["next_steps"] = self.next_steps
        return payload


class GatewayValidationError(GatewayError):
    def __init__(self, message: str, details: dict | None = None, next_steps: list[str] | None = None):
        super().__init__(
            code="gateway_validation_error",
            message=message,
            status_code=422,
            details=details,
            next_steps=next_steps,
        )


class GatewayPermissionDenied(GatewayError):
    def __init__(self, message: str = "Access denied for this operation."):
        super().__init__(
            code="gateway_permission_denied",
            message=message,
            status_code=403,
        )


class GatewayNotFoundError(GatewayError):
    def __init__(self, message: str):
        super().__init__(
            code="gateway_not_found",
            message=message,
            status_code=404,
        )


class GatewayConflictError(GatewayError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(
            code="gateway_conflict",
            message=message,
            status_code=409,
            details=details,
        )
