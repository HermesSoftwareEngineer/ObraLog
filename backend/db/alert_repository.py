from uuid import UUID

from backend.db.models import Alert, AlertRead


async def create_alert(*args, **kwargs) -> Alert:
    """Cria um novo alerta de campo e retorna a entidade persistida."""
    ...


async def get_alert_by_id(alert_id: UUID) -> Alert | None:
    """Busca um alerta pelo seu identificador único."""
    ...


async def get_alert_by_code(code: str) -> Alert | None:
    """Busca um alerta pelo código legível de negócio."""
    ...


async def list_alerts(status: str | None = None) -> list[Alert]:
    """Lista alertas com filtro opcional por status."""
    ...


async def update_alert_status(alert_id: UUID, status: str, resolved_by: UUID | None) -> Alert:
    """Atualiza status do alerta e registra resolvedor quando aplicável."""
    ...


async def mark_as_read(alert_id: UUID, worker_id: UUID) -> AlertRead:
    """Marca um alerta como lido por um colaborador e retorna o registro de leitura."""
    ...


async def list_unread_by_worker(worker_id: UUID) -> list[Alert]:
    """Lista alertas não lidos por colaborador."""
    ...


async def generate_alert_code() -> str:
    """Gera código incremental no formato ALT-YYYY-NNNN."""
    ...
