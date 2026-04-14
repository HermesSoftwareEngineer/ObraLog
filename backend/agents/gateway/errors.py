from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GatewayError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: dict | None = None

    def to_dict(self) -> dict:
        payload = {
            "ok": False,
            "error": self.message,
            "code": self.code,
        }
        if self.details:
            payload["details"] = self.details
        return payload


class GatewayValidationError(GatewayError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(
            code="gateway_validation_error",
            message=message,
            status_code=422,
            details=details,
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
