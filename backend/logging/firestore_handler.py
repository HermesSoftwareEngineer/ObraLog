import logging
import os
import smtplib
import threading
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

_STANDARD_ATTRS = frozenset({
    "args", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "message", "module", "msecs", "msg",
    "name", "pathname", "process", "processName", "relativeCreated",
    "stack_info", "thread", "threadName", "tenant_id", "request_id",
    "taskName",
})

_client = None
_client_lock = threading.Lock()


def _get_client():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                import google.cloud.firestore
                _client = google.cloud.firestore.Client(
                    project=os.getenv("GCP_PROJECT_ID")
                )
    return _client


def _get_message(record: logging.LogRecord) -> str:
    msg = record.getMessage()
    if record.exc_info and not record.exc_text:
        record.exc_text = logging.Formatter().formatException(record.exc_info)
    if record.exc_text:
        msg = f"{msg}\n{record.exc_text}"
    return msg


class LogContextFilter(logging.Filter):
    """Injeta tenant_id e request_id do contexto Flask em cada LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from flask import g, has_request_context
            if has_request_context():
                record.tenant_id = getattr(g, "tenant_id", None)
                record.request_id = getattr(g, "_request_id", None)
            else:
                record.tenant_id = None
                record.request_id = None
        except Exception:
            record.tenant_id = None
            record.request_id = None
        return True


class FirestoreHandler(logging.Handler):
    """Persiste logs no Firestore e envia e-mail para alertas CRITICAL."""

    def __init__(self, collection: str = "logs", ttl_days: int = 90) -> None:
        super().__init__()
        self._collection = collection
        self._ttl_days = ttl_days

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._write(record)
        except Exception:
            self.handleError(record)
            return

        if record.levelno >= logging.CRITICAL:
            threading.Thread(
                target=self._send_email,
                args=(record,),
                daemon=True,
            ).start()

    def _write(self, record: logging.LogRecord) -> None:
        now = datetime.now(timezone.utc)
        extra = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _STANDARD_ATTRS
            and isinstance(v, (str, int, float, bool, type(None)))
        }
        doc = {
            "timestamp": now,
            "level": record.levelname,
            "module": record.name,
            "message": _get_message(record),
            "tenant_id": getattr(record, "tenant_id", None),
            "request_id": getattr(record, "request_id", None),
            "extra": extra,
            "expire_at": now + timedelta(days=self._ttl_days),
        }
        _get_client().collection(self._collection).add(doc)

    def _send_email(self, record: logging.LogRecord) -> None:
        gmail_user = os.getenv("GMAIL_USER", "")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD", "")
        if not gmail_user or not gmail_password:
            return
        try:
            body = (
                f"Nível:    {record.levelname}\n"
                f"Módulo:   {record.name}\n"
                f"Mensagem: {_get_message(record)}\n"
                f"Tenant:   {getattr(record, 'tenant_id', None)}\n"
                f"Request:  {getattr(record, 'request_id', None)}\n"
            )
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = f"[ObraLog CRITICAL] {record.name}"
            msg["From"] = gmail_user
            msg["To"] = gmail_user
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(gmail_user, gmail_password)
                server.send_message(msg)
        except Exception:
            pass
