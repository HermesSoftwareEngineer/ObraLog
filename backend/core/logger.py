import logging
import sys

# Configura logging para aparecer no console com flush
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)s in %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Desabilita buffer para garantir que logs apareçam
logging.getLogger().handlers[0].flush = sys.stdout.flush

logger = logging.getLogger("diario_obra")
logger.setLevel(logging.DEBUG)
