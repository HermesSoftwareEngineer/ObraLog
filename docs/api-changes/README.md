# Histórico de Alterações da API

Documentação de todas as mudanças realizadas na API do ObraLog.

## 📋 Índice de Alterações

### 2026-04-05
- **[Alterações em Frentes de Serviço e Registros](./20260405_alteracoes_frente_registros.md)**
  - ✨ Campo `observacao` adicionado em ambas as tabelas
  - 🔄 `frente_servico_id` agora é obrigatório em Registros
  - ❌ Campo `hora_registro` removido de Registros
  - 🔄 Campos `data` e `usuario_registrador_id` agora opcionais em Registros

## 📊 Status dos Endpoints

Veja [STATUS_ENDPOINTS.md](./STATUS_ENDPOINTS.md) para um resumo do status de cada endpoint e sua data de última alteração.

---

## Como Usar Esta Documentação

Cada arquivo `.md` nesta pasta documenta as alterações de uma data específica ou grupo de alterações relacionadas.

### Estrutura de cada arquivo:
1. **Resumo** - O quê e por quê foi alterado
2. **Endpoints afetados** - Cada endpoint com antes/depois
3. **Breaking changes** - Se houver incompatibilidades
4. **Guia de migração** - Como adaptar seu código

### Checklist para atualizar o cliente:
- [ ] Ler o arquivo `.md` da alteração
- [ ] Identificar se há breaking changes
- [ ] Atualizar requisições (se necessário)
- [ ] Atualizar tratamento de respostas
- [ ] Testar com a nova API
- [ ] Manter histórico de versão do cliente

---
