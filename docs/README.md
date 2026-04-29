# Documentação - ObraLog

Documentação técnica, operacional e de referência para o projeto ObraLog.

---

## 📚 Índice

### 🤖 Agent Diário (Telegram Bot)

O Agent Diário é o assistente de Telegram que conversa naturalmente com pessoal de obra.

| Documento | Público | Descrição |
|-----------|---------|-----------|
| **[PROMPT_AGENT_DIARIO.md](./PROMPT_AGENT_DIARIO.md)** | Desenvolvedores | Prompt completo do agent com todos os fluxos, regras e exemplos |
| **[GUIA_RAPIDO_AGENTE.md](./GUIA_RAPIDO_AGENTE.md)** | Todos | Resumo executivo, números importantes, checklist de implementação |
| **[CONTEXTO_E_MEMORIA_AGENTE.md](./CONTEXTO_E_MEMORIA_AGENTE.md)** | Arquitetos/DevOps | Explicação técnica de contexto, limites, memória e reinserção |
| **[MEMORY_PROMPT_AGENTE.md](./MEMORY_PROMPT_AGENTE.md)** | Desenvolvedores IA | Formato de memória para reinserção automática em contextos longos |

---

### 🔄 Alterações e Versionamento da API

| Documento | Descrição |
|-----------|-----------|
| **[../CHANGELOG.md](../CHANGELOG.md)** | Registro cronológico de todas as alterações |
| **[../API_MAPEAMENTO.md](../API_MAPEAMENTO.md)** | Documentação oficial dos endpoints (sempre atualizada) |
| **[../docs/api-changes/](../docs/api-changes/)** | Pasta com detalhes de cada alteração + guias de migração |

---

### 🗄️ Banco de Dados

| Documento | Descrição |
|-----------|-----------|
| **[DB_DESENHO_TECNICO_20260414.md](./DB_DESENHO_TECNICO_20260414.md)** | Desenho técnico do banco com ingestão de mensagens, lançamentos e ajustes de integridade |

---

## 🎯 Como Usar Esta Documentação

### Se você é...

**Um Developer implementando o Agent:**
1. Leia [PROMPT_AGENT_DIARIO.md](./PROMPT_AGENT_DIARIO.md) para entender todos os fluxos
2. Consulte [MEMORY_PROMPT_AGENTE.md](./MEMORY_PROMPT_AGENTE.md) para implementar memória
3. Use [GUIA_RAPIDO_AGENTE.md](./GUIA_RAPIDO_AGENTE.md) como checklist de implementação

**Um Arquiteto/Tech Lead:**
1. Veja [GUIA_RAPIDO_AGENTE.md](./GUIA_RAPIDO_AGENTE.md) para visão geral
2. Leia [CONTEXTO_E_MEMORIA_AGENTE.md](./CONTEXTO_E_MEMORIA_AGENTE.md) para decisões de arquitetura
3. Consulte limites e recomendações para stack

**Um QA testando o Agent:**
1. Leia [GUIA_RAPIDO_AGENTE.md](./GUIA_RAPIDO_AGENTE.md) — seção "Testes Recomendados"
2. Use [PROMPT_AGENT_DIARIO.md](./PROMPT_AGENT_DIARIO.md) como referência de comportamento esperado
3. Valide contra "Regras Inegociáveis" e "Edge Cases"

**Um Developer da API:**
1. Consulte [../API_MAPEAMENTO.md](../API_MAPEAMENTO.md) para endpoints
2. Veja [../docs/api-changes/](../docs/api-changes/) para entender últimas mudanças
3. Leia [../CHANGELOG.md](../CHANGELOG.md) para histórico

**Um Product Manager/PO:**
1. Veja [GUIA_RAPIDO_AGENTE.md](./GUIA_RAPIDO_AGENTE.md) para duração de fluxos e UX
2. Consulte [../API_MAPEAMENTO.md](../API_MAPEAMENTO.md) para funcionalidades disponíveis
3. Revise [../docs/api-changes/](../docs/api-changes/) para impacto de mudanças

---

## 📊 Resumo Rápido

### O que o Agent Faz
- ✅ Primeiro contato: cadastra usuário (nome, função, obra, turno, etc)
- ✅ Registra produtividade diária (atividade, quantidade, local)
- ✅ Relata problemas com equipamentos
- ✅ Consulta histórico de registros
- ✅ Atualiza dados cadastrais
- ✅ Adapta tom conforme estilo do usuário

### Limites Técnicos
- **100k tokens** de contexto por sessão
- **~80-100 mensagens** antes de memória se ativar
- **24-48 horas** de conversas ativas em uma sessão

### Regras Inegociáveis
- 🚫 Nunca salva sem confirmação explícita
- 🚫 Uma informação por mensagem no cadastro
- 🚫 Nunca inventa dados ou usa jargão técnico
- 🚫 Sempre adapta tom ao usuário
- 🚫 Sempre chama pelo apelido/primeiro nome

---

## 🔗 Documentação Complementar

- **[../API_MAPEAMENTO.md](../API_MAPEAMENTO.md)** — Endpoints REST da API
- **[../CHANGELOG.md](../CHANGELOG.md)** — Histórico de versões
- **[../README.md](../README.md)** — Visão geral do projeto

---

## ❓ Perguntas Frequentes

**P: O agente pode usar IA?**
A: Sim, é construído com LLM (Claude, GPT, etc). O prompt determina comportamento.

**P: Como funciona a memória?**
A: Quando contexto fica longo (~70%), sistema reinsere resumo automaticamente. Veja [CONTEXTO_E_MEMORIA_AGENTE.md](./CONTEXTO_E_MEMORIA_AGENTE.md).

**P: O usuário vê o Memory Prompt?**
A: Não, é processado internamente e não aparece para o usuário.

**P: Qual o limite de tokens?**
A: ~100k tokens por sessão. Veja [CONTEXTO_E_MEMORIA_AGENTE.md](./CONTEXTO_E_MEMORIA_AGENTE.md) para detalhes.

**P: Posso customizar o tom?**
A: Sim! Agent adapta automaticamente. Veja seção de "Postura e Tom" em [PROMPT_AGENT_DIARIO.md](./PROMPT_AGENT_DIARIO.md).

---

## 📝 Versionamento

| Versão | Data | Mudanças |
|--------|------|----------|
| 1.0 | 2026-04-05 | Versão inicial com prompts completos e documentação de contexto/memória |

---
