print("[BOOT] chat_db.py: módulo carregando...", flush=True)
import logging
import os
import time
from dotenv import load_dotenv

load_dotenv()

_logger = logging.getLogger("obralog.chat_db")

DB_URI = os.environ.get("DATABASE_URL")
print(f"[BOOT] chat_db.py: DATABASE_URL presente={bool(DB_URI)}", flush=True)

if not DB_URI:
	raise RuntimeError("DATABASE_URL não configurada. O sistema não pode iniciar sem checkpointer.")

try:
	print("[BOOT] chat_db.py: importando psycopg_pool/PostgresSaver...", flush=True)
	from psycopg_pool import ConnectionPool
	from psycopg.rows import dict_row
	from langgraph.checkpoint.postgres import PostgresSaver
	print("[BOOT] chat_db.py: psycopg_pool/PostgresSaver OK", flush=True)

	pool_min_size = int(os.environ.get("CHECKPOINTER_POOL_MIN_SIZE", "1"))
	pool_max_size = int(os.environ.get("CHECKPOINTER_POOL_MAX_SIZE", "5"))

	print(f"[BOOT] chat_db.py: criando ConnectionPool min={pool_min_size} max={pool_max_size}...", flush=True)
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
	_elapsed_pool = time.monotonic() - _t
	print(f"[BOOT] chat_db.py: ConnectionPool criado em {_elapsed_pool:.2f}s", flush=True)
	_logger.info("[CHAT_DB] ConnectionPool criado em %.2fs", _elapsed_pool)

	print("[BOOT] chat_db.py: instanciando PostgresSaver...", flush=True)
	checkpointer = PostgresSaver(pool)
	print("[BOOT] chat_db.py: PostgresSaver instanciado", flush=True)

	print("[BOOT] chat_db.py: checkpointer.setup() INICIANDO (DDL LangGraph)...", flush=True)
	_logger.info("[CHAT_DB] checkpointer.setup() iniciado (cria tabelas do LangGraph se não existirem)")
	_t = time.monotonic()
	checkpointer.setup()
	_elapsed_setup = time.monotonic() - _t
	print(f"[BOOT] chat_db.py: checkpointer.setup() CONCLUÍDO em {_elapsed_setup:.2f}s", flush=True)
	_logger.info("[CHAT_DB] checkpointer.setup() concluído em %.2fs", _elapsed_setup)
except ImportError as exc:
	print(f"[BOOT] chat_db.py: ImportError — {exc}", flush=True)
	raise RuntimeError("Dependências do checkpointer não disponíveis. Instale psycopg/libpq corretamente.") from exc
except Exception as exc:
	print(f"[BOOT] chat_db.py: ERRO FATAL — {exc}", flush=True)
	_logger.critical(
		"Falha ao inicializar checkpointer Postgres: %s", exc, exc_info=True
	)
	raise RuntimeError("Falha ao inicializar o schema do checkpointer no Postgres.") from exc
