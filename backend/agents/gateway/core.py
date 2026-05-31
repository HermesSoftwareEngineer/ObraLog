"""
Núcleo do gateway: duas funções que envolvem qualquer operação com
checagem de permissão, validação de intenção e log estruturado.

Uso:
    def handler() -> dict:
        # lógica de negócio da tool (opera por closure, sem parâmetros)
        ...
    return run_consulta(actor_level, actor_user_id, "nome_da_op", handler)
    return run_execucao(actor_level, actor_user_id, "nome_da_op", intent, handler)
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone

from .errors import GatewayError, GatewayPermissionDenied, GatewayValidationError
from .policies import GatewayPolicyService

logger = logging.getLogger("obralog.gateway")

# Instância compartilhada — policies são stateless, não precisam ser reinstanciadas por chamada
_policies = GatewayPolicyService()


def run_consulta(
    actor_level: str,
    actor_user_id: int,
    operation: str,
    handler: Callable[[], dict],
) -> dict:
    """Executa operação de leitura: checa permissão, roda handler, loga e retorna dict."""
    started = time.perf_counter()
    try:
        _policies.assert_can_read(actor_level)
        data = _safe_call(operation, handler)
        _log("consulta", operation, actor_user_id, actor_level, ok=True, ms=_ms(started), data=data)
        return {"ok": True, "operation": operation, **data}
    except GatewayError as exc:
        _log("consulta", operation, actor_user_id, actor_level, ok=False, ms=_ms(started), error=exc.message)
        return exc.to_dict()


def run_execucao(
    actor_level: str,
    actor_user_id: int,
    operation: str,
    intent: str,
    handler: Callable[[], dict],
) -> dict:
    """Executa operação de escrita: checa permissão, valida intenção, roda handler, loga e retorna dict."""
    started = time.perf_counter()
    try:
        _policies.assert_can_write(actor_level)
        _policies.assert_execution_intent(intent)
        data = _safe_call(operation, handler)
        _log("execucao", operation, actor_user_id, actor_level, ok=True, ms=_ms(started), data=data)
        return {"ok": True, "operation": operation, **data}
    except GatewayError as exc:
        _log("execucao", operation, actor_user_id, actor_level, ok=False, ms=_ms(started), error=exc.message)
        return exc.to_dict()


def _safe_call(operation: str, handler: Callable[[], dict]) -> dict:
    """Executa o handler convertendo exceções genéricas para GatewayError tipado."""
    try:
        return handler() or {}
    except GatewayError:
        raise
    except PermissionError as exc:
        raise GatewayPermissionDenied(str(exc) or "Acesso negado para esta operação.") from exc
    except ValueError as exc:
        raise GatewayValidationError(message=str(exc), details={"operation": operation}) from exc
    except Exception as exc:
        raise GatewayError(
            code="gateway_unexpected_error",
            message=str(exc),
            status_code=500,
            details={"operation": operation},
        ) from exc


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _log(
    route: str,
    operation: str,
    actor_user_id: int,
    actor_level: str,
    *,
    ok: bool,
    ms: int,
    data: dict | None = None,
    error: str | None = None,
) -> None:
    event = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "ok": ok,
        "duration_ms": ms,
        "route": route,
        "operation": operation,
        "actor_user_id": actor_user_id,
        "actor_level": actor_level,
    }
    if ok and isinstance(data, dict):
        event["result_keys"] = sorted(list(data.keys()))[:20]
    elif error:
        event["error"] = error
    logger.info("gateway_call %s", json.dumps(event, ensure_ascii=False))
