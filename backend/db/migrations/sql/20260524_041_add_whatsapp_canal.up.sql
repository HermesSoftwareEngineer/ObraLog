-- Add WHATSAPP value to canal_origem_mensagem enum
-- IF NOT EXISTS requires Postgres 9.6+; Supabase supports it.
ALTER TYPE canal_origem_mensagem ADD VALUE IF NOT EXISTS 'whatsapp';
