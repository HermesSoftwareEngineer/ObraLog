from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ActorContext:
    actor_user_id: int
    actor_level: str


@dataclass(frozen=True)
class GatewayRequestMeta:
    operation: str
    action_route: str = "consulta"
    intent: str | None = None
    business_tool: str | None = None
    technical_operation: str | None = None
    request_id: str | None = None
    source: str = "agent"
    occurred_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class GatewayRequest:
    actor: ActorContext
    meta: GatewayRequestMeta
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewayResponse:
    ok: bool
    operation: str
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "operation": self.operation,
        }
        payload.update(self.data)
        if self.warnings:
            payload["warnings"] = self.warnings
        return payload


@dataclass(frozen=True)
class WriteOptions:
    require_confirmation: bool = True
    confirmed: bool = False
