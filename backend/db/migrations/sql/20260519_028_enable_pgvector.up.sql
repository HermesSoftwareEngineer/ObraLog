-- Migration 028: Enable pgvector extension
-- Date: 2026-05-19

CREATE EXTENSION IF NOT EXISTS vector;
