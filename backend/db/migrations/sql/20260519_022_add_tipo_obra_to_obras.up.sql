-- Migration 022: Add tipo_obra to obras
-- Date: 2026-05-19

ALTER TABLE obras ADD COLUMN IF NOT EXISTS tipo_obra VARCHAR(50);
-- valores esperados: 'rodovia', 'edificacao'
