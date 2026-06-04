import os
from dotenv import load_dotenv

load_dotenv()

DB_URI = os.environ.get("DATABASE_URL")

if not DB_URI:
	raise RuntimeError("DATABASE_URL não configurada. O sistema não pode iniciar sem checkpointer.")

try:
	from psycopg_pool import ConnectionPool
	from psycopg.rows import dict_row
	from langgraph.checkpoint.postgres import PostgresSaver

	pool_min_size = int(os.environ.get("CHECKPOINTER_POOL_MIN_SIZE", "1"))
	pool_max_size = int(os.environ.get("CHECKPOINTER_POOL_MAX_SIZE", "5"))

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
		},
	)
	checkpointer = PostgresSaver(pool)
	checkpointer.setup()
except ImportError as exc:
	raise RuntimeError("Dependências do checkpointer não disponíveis. Instale psycopg/libpq corretamente.") from exc
except Exception as exc:
	import logging as _logging
	_logging.getLogger("obralog.chat_db").critical(
		"Falha ao inicializar checkpointer Postgres: %s", exc, exc_info=True
	)
	raise RuntimeError("Falha ao inicializar o schema do checkpointer no Postgres.") from exc
