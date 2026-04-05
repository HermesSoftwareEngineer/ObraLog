import os
from dotenv import load_dotenv

load_dotenv()

DB_URI = os.environ.get("DATABASE_URL")

if not DB_URI:
	raise RuntimeError("DATABASE_URL não configurada. O sistema não pode iniciar sem checkpointer.")

try:
	from psycopg import Connection
	from psycopg.rows import dict_row
	from langgraph.checkpoint.postgres import PostgresSaver

	# Use a single Connection with prepare_threshold=None to avoid pool-related prepared-statement races
	conn = Connection.connect(DB_URI, autocommit=True, prepare_threshold=None, row_factory=dict_row)
	checkpointer = PostgresSaver(conn)
	checkpointer.setup()
except ImportError as exc:
	raise RuntimeError("Dependências do checkpointer não disponíveis. Instale psycopg/libpq corretamente.") from exc
except Exception as exc:
	raise RuntimeError("Falha ao inicializar o schema do checkpointer no Postgres.") from exc
