-- Migration 029: Add timeout_conversa_minutos to tenants
-- Date: 2026-05-19

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS timeout_conversa_minutos INT NOT NULL DEFAULT 60;
