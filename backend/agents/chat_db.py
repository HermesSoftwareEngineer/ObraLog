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
	pool = ConnectionPool(
		conninfo=DB_URI,
		min_size=pool_min_size,
		max_size=pool_max_size,
		kwargs={
			"autocommit": True,
			"prepare_threshold": None,
			"row_factory": dict_row,
		},
	)
	checkpointer = PostgresSaver(pool)
	checkpointer.setup()
except ImportError as exc:
	raise RuntimeError("Dependências do checkpointer não disponíveis. Instale psycopg/libpq corretamente.") from exc
except Exception as exc:
	raise RuntimeError("Falha ao inicializar o schema do checkpointer no Postgres.") from exc
