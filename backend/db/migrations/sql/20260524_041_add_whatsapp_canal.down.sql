-- Enum values cannot be removed in PostgreSQL without recreating the type.
-- To rollback: ensure no rows use canal='whatsapp', then recreate the type.
-- This is intentionally left as a no-op; handle manually if needed.
SELECT 1;
