# Fase 3 - Conversao de API

## Objetivo
Converter a API para operar apenas com registros e status, sem depender de migracao de dados.

## Backlog
- [ ] Remover ou desativar endpoints de lancamentos da API publica.
- [ ] Expor somente endpoints de registros e status.
- [ ] Ajustar payloads de registro para aceitar criacao parcial.
- [ ] Garantir regra de consolidacao apenas no status consolidado.
- [ ] Atualizar contratos e documentacao para nao mencionar rascunho/lancamento.

## Criterios de Aceite
- [ ] API publica nao depende de migracao de dados para funcionar.
- [ ] Endpoints de registros suportam criacao e atualizacao parcial.
- [ ] Fluxo oficial nao menciona rascunho/lancamento para o usuario final.
