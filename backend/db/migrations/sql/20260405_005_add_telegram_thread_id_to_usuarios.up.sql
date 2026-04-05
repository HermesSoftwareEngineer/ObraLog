-- Adiciona thread_id persistente por usuário para controle de contexto no agente
ALTER TABLE usuarios
ADD COLUMN telegram_thread_id VARCHAR UNIQUE;

-- Inicializa com o chat_id existente quando disponível
UPDATE usuarios
SET telegram_thread_id = telegram_chat_id
WHERE telegram_chat_id IS NOT NULL;

CREATE UNIQUE INDEX idx_usuarios_telegram_thread_id_unique
ON usuarios(telegram_thread_id)
WHERE telegram_thread_id IS NOT NULL;
