from .base import api_blueprint

# Import order matters only for side effects (route registration).
from . import agent_instructions  # noqa: F401
from . import usuarios  # noqa: F401
from . import frentes_servico  # noqa: F401
from . import registros  # noqa: F401
from . import operacional  # noqa: F401

__all__ = ["api_blueprint"]
