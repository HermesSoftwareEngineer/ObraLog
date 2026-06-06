import logging
import os
import time
from dotenv import load_dotenv

load_dotenv()

_logger = logging.getLogger("obralog.chat_db")

DB_URI = os.environ.get("DATABASE_URL")

if not DB_URI:
	raise RuntimeError("DATABASE_URL não configurada. O sistema não pode iniciar sem checkpointer.")

try:
	from psycopg_pool import ConnectionPool
	from psycopg.rows import dict_row
	from langgraph.checkpoint.postgres import PostgresSaver

	pool_min_size = int(os.environ.get("CHECKPOINTER_POOL_MIN_SIZE", "1"))
	pool_max_size = int(os.environ.get("CHECKPOINTER_POOL_MAX_SIZE", "5"))

	_logger.info("[CHAT_DB] criando ConnectionPool min=%d max=%d", pool_min_size, pool_max_size)
	_t = time.monotonic()
	# Use a pool so closed/stale connections are replaced automatically in long-lived prod workers.
	# reconnect_timeout ensures the pool keeps trying to rebuild connections after a server bounce.
	pool = ConnectionPool(
		conninfo=DB_URI,
		min_size=pool_min_size,
		max_size=pool_max_size,
		reconnect_timeout=30,
		kwargs={
			"autocommit": True,
			"prepare_threshold": None,
			"row_factory": dict_row,
			"keepalives": 1,
			"keepalives_idle": 25,
			"keepalives_interval": 10,
			"keepalives_count": 5,
			# connect_timeout: aborta tentativa de conexão TCP se o servidor não
			# responder em 10s — sem isso, o pool pode esperar indefinidamente.
			"connect_timeout": 10,
		},
	)
	_logger.info("[CHAT_DB] ConnectionPool criado em %.2fs", time.monotonic() - _t)

	checkpointer = PostgresSaver(pool)

	_logger.info("[CHAT_DB] checkpointer.setup() iniciado (cria tabelas do LangGraph se não existirem)")
	_t = time.monotonic()
	checkpointer.setup()
	_logger.info("[CHAT_DB] checkpointer.setup() concluído em %.2fs", time.monotonic() - _t)
except ImportError as exc:
	raise RuntimeError("Dependências do checkpointer não disponíveis. Instale psycopg/libpq corretamente.") from exc
except Exception as exc:
	_logger.critical(
		"Falha ao inicializar checkpointer Postgres: %s", exc, exc_info=True
	)
	raise RuntimeError("Falha ao inicializar o schema do checkpointer no Postgres.") from exc
