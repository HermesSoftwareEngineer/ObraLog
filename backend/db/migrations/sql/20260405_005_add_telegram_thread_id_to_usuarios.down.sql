DROP INDEX IF EXISTS idx_usuarios_telegram_thread_id_unique;

ALTER TABLE usuarios
DROP COLUMN IF EXISTS telegram_thread_id;
