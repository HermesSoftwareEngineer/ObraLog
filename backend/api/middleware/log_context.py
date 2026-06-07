import uuid
from flask import g


def set_request_id() -> None:
    """Gera request_id único por requisição para rastreamento nos logs."""
    g._request_id = uuid.uuid4().hex[:12]
