# Fase 1 - Preparacao de Banco (Sem Quebra)

## Objetivo
Preparar o banco para operar com registro unico com status, mantendo compatibilidade temporaria.

## Backlog
- [ ] Criar enum de status de registro (ex.: pendente, consolidado, revisado, ativo, descartado).
- [ ] Adicionar coluna status em registros com default pendente.
- [ ] Tornar campos basicos de registros opcionais no schema fisico (remover NOT NULL dos campos de negocio).
- [ ] Criar regra condicional no banco: se status = consolidado, exigir campos basicos preenchidos.
- [ ] Garantir indexes para consultas por status e data.
- [ ] Manter tabelas de lancamento temporariamente para compatibilidade.

## Criterios de Aceite
- [ ] Migracoes aplicam sem erro em base nova e base existente.
- [ ] Registros novos podem ser criados sem campos basicos quando status nao for consolidado.
- [ ] Tentativa de consolidar sem campos basicos falha por regra de integridade.
