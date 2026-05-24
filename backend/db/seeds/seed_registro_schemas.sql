-- Seed: Schemas padrão de registro por tipo de obra
-- Execute MANUALMENTE no Supabase após rodar a migration 026.
-- Substitua o valor de tenant_id abaixo pelo tenant_id correto antes de executar.
--
-- Este script é idempotente: ON CONFLICT DO NOTHING garante que re-execuções
-- não sobrescrevem dados existentes.

-- substitua pelo tenant_id correto
\set tenant_id 1

INSERT INTO registro_schemas (tenant_id, tipo_obra, nome, campos_ativos, campos_extras, ativo)
VALUES
(
    :tenant_id,
    'rodovia',
    'Padrão Rodovia',
    '{"estaca_inicial": true, "estaca_final": true, "lado_pista": true, "tempo_manha": true, "tempo_tarde": true, "resultado": true, "frente_servico": true}',
    '[]',
    true
),
(
    :tenant_id,
    'edificacao',
    'Padrão Edificação',
    '{"tempo_manha": true, "tempo_tarde": true, "resultado": true, "frente_servico": true}',
    '[]',
    true
)
ON CONFLICT (tenant_id, tipo_obra) DO NOTHING;
