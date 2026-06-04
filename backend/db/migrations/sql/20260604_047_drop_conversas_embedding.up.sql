-- Migration 047: Remove coluna embedding de conversas (busca vetorial desativada)
ALTER TABLE conversas DROP COLUMN IF EXISTS embedding;
