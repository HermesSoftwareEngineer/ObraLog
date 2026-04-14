# Fase 4 - Remocao Definitiva de Rascunho/Lancamentos

## Objetivo
Eliminar completamente o conceito de rascunho/lancamento de codigo e banco.

## Backlog
- [x] Remover classes Lancamento* de modelos ORM.
- [x] Remover repositorios e tools de lancamentos.
- [x] Remover rotas /lancamentos e operacoes relacionadas.
- [x] Remover mappers e testes que dependem de lancamentos.
- [x] Limpar enums e tipos SQL de lancamento.
- [x] Dropar tabelas de lancamentos em migracao final.

## Criterios de Aceite
- [x] Nao existe referencia funcional a rascunho/lancamento no backend.
- [x] Suite de testes relevante passa sem fixtures de lancamentos.
- [x] Banco final nao possui tabelas/enum de lancamento.
