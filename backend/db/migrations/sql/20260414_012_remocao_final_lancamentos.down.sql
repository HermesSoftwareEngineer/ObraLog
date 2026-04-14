-- Migracao sem rollback automatico: estruturas de lancamento foram removidas definitivamente.
DO $$
BEGIN
    RAISE NOTICE '20260414_012_remocao_final_lancamentos: rollback manual requerido para restaurar estruturas de lancamento.';
END $$;
