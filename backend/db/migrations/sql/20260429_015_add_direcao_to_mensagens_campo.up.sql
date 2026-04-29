-- Migration: Add direcao field to mensagens_campo
-- Date: 2026-04-29
-- Description: Add message direction (user/agent) tracking to mensagens_campo table

-- Create ENUM type for message direction
CREATE TYPE direcao_mensagem AS ENUM ('user', 'agent');

-- Add direcao column to mensagens_campo with default value 'user'
ALTER TABLE mensagens_campo
ADD COLUMN direcao direcao_mensagem NOT NULL DEFAULT 'user';

-- Create index on direcao for better query performance
CREATE INDEX idx_mensagens_campo_direcao ON mensagens_campo (direcao);

-- Create composite index on telegram_chat_id and direcao for common queries
CREATE INDEX idx_mensagens_campo_chat_direcao ON mensagens_campo (telegram_chat_id, direcao);
