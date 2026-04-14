# Fase 2 - Codigo Registro-First

## Objetivo
Migrar backend, API e agente para fluxo unico de registros com status.

## Backlog
- [ ] Atualizar modelos ORM para status em Registro.
- [ ] Remover dependencia funcional de Lancamento* em repositorios e services.
- [ ] Ajustar criacao e atualizacao de registro para payload parcial.
- [ ] Criar operacao de transicao de status de registro com validacao de negocio.
- [ ] Remover regras de prompt que priorizam rascunho.
- [ ] Atualizar gateway para operar somente com registros.
- [ ] Atualizar validacoes do node de resposta para nao bloquear criacao parcial.

## Criterios de Aceite
- [ ] Fluxo principal do agente cria/atualiza registros sem mencionar rascunho.
- [ ] Consolidacao so ocorre quando campos basicos estiverem completos.
- [ ] Endpoints antigos de lancamento ficam desativados ou marcados para retirada controlada.
