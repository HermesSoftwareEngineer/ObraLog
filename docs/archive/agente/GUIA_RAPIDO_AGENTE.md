# Guia Rápido - Agent Diário

Resumo técnico e operacional do agent para referência rápida.

---

## 🎯 O Agent em Uma Frase

**Assistente de Telegram que conversa naturalmente com pessoal de obra para registrar produtividade, problemas e dados, de forma amigável e sem parecer um sistema.**

---

## 📊 Números Importantes

| Métrica | Valor | Notas |
|---------|-------|-------|
| Limite de contexto | ~100k tokens | Por sessão |
| Duração típica | 80-100 mensagens | Antes de memória ativar |
| Tempo de sessão | 24-48 horas | De conversas ativas |
| Trigger de memória | ~70% contexto | Reinsere automaticamente |
| Histórico recente mantido | Últimas 50 msg | De cada conversa |

---

## 🛠️ Fluxos Principais

### 1. Primeiro Contato (não cadastrado)
```
Cumprimento → Nome → Função → Obra → 
Apelido (opt) → Telefone (opt) → Turno (opt) → 
Resumo → Confirmação → Salva
```
**Duração:** 8-12 mensagens

### 2. Usuário Cadastrado - Registrar Produção
```
Reconhece intenção → 
Coleta: O quê + Quanto + Onde (opt) → 
Observação (opt) → 
Resumo → Confirmação → Salva
```
**Duração:** 4-7 mensagens

### 3. Usuário Cadastrado - Relatar Problema
```
Reconhece intenção →
Coleta: Equipamento + Problema →
Foto (opt) →
Resumo → Confirmação → Salva + Notifica
```
**Duração:** 4-6 mensagens

### 4. Consultar Registros
```
Identifica período (hoje/semana/mês) →
Recupera dados →
Exibe de forma clara
```
**Duração:** 1-2 mensagens

### 5. Atualizar Cadastro
```
Mostra dados atuais →
Pergunta o que mudar →
Aplica mudança →
Resumo atualizado →
Confirmação → Salva
```
**Duração:** 3-5 mensagens

---

## 🎭 Adaptação de Tom

### Detecção
- **Formal?** Mantém profissional, claro
- **Informal?** Relaxa tom, pode usar emojis, acompanha gírias
- **Rápido/impaciente?** Respostas curtas e diretas
- **Dúvidas frequentes?** Mais explicativo

### Resposta
Sempre mantém:
- ✅ Clareza
- ✅ Paciência
- ✅ Respeito
- ✅ Confirmação antes de salvar

---

## 📋 Checklist de Implementação

### Backend/API
- [ ] Endpoints POST/PUT para registros implementados?
- [ ] GET /registros com filtros por data/frente/usuário?
- [ ] Campo `created_at` automático em registros?
- [ ] Notificação de problema de equipamento para admin?
- [ ] Validação de frente_servico_id (obrigatório)?

### Agente/LLM
- [ ] MEMORY PROMPT v1 reinsertado automaticamente?
- [ ] Histórico limitado a últimas 50 msg quando memória ativa?
- [ ] Regeneração de memory block a cada ~2h ou ~50 msg?
- [ ] Token counter implementado (dispara em ~70%)?
- [ ] Usuário já registrado sempre usa apelido/primeiro nome?

### Telegram Bot
- [ ] /start → redireciona para agent Diário?
- [ ] chat_id capturado e vinculado a user_id?
- [ ] Mensagens de áudio retornam "ainda não consigo ouvir"?
- [ ] Confirmações de save vão para user (não só agent)?

### Dados/Banco
- [ ] Tabela: usuarios (com telefone, turno, obra_id)?
- [ ] Tabela: frentes_servico (com observacao)?
- [ ] Tabela: registros (com observacao, created_at)?
- [ ] Índices em (usuario_id, data, frente_servico_id)?

---

## 🚨 Erros Comuns

### ❌ Agent Salva Sem Confirmação
- **Causa:** Não detecta padrões de confirmação
- **Fix:** Whitelist de respostas: sim|yep|ok|certo|confirma|pode salvar|tá bom

### ❌ Agent Pede Tudo de Uma Vez
- **Causa:** Tenta ser eficiente, demanda todas as infos
- **Fix:** Force sequence de mensagens individuais no prompt

### ❌ Agent Inventa Informação
- **Causa:** Alucinação do LLM
- **Fix:** Instrução clara "Se não sabe, diz que não sabe" + temperatura baixa

### ❌ Agent Não Adapta Tom
- **Causa:** Prompt genérico demais
- **Fix:** Memória preserva estilo detectado; instrução explícita de adaptação

### ❌ Contexto Sai do Controle
- **Causa:** Memória não é reinserida a tempo
- **Fix:** Token counter + regeneração automática a cada~70% uso

### ❌ Usuário Perde Dados Entre Sessões
- **Causa:** Memória não inclui dados críticos
- **Fix:** Sempre reinsire: nome, apelido, função, obra, telefone, turno

---

## 🧪 Testes Recomendados

### Teste 1: Cadastro Completo
```
✓ Cumprimento é amigável
✓ Uma informação por mensagem
✓ Resumo mostra TODOS os campos
✓ Salva apenas após confirmação explícita
✓ Resposta final instrui sobre próximos passos
```

### Teste 2: Registro de Produção
```
✓ Reconhece intenção naturalmente
✓ Coleta campos na ordem certa
✓ Calcula resultado se estacas forem dadas
✓ Resumo é claro e preciso
✓ Salva no banco corretamente
```

### Teste 3: Tom Adaptativo
```
✓ Usuário formal → resposta formal
✓ Usuário casual → resposta descontraída
✓ Emojis ajustados ao estilo
✓ Linguagem nunca fica robótica
```

### Teste 4: Contexto/Memória
```
✓ 50+ mensagens → memória não sai do contexto
✓ Pausa 5min + nova mensagem → memória reinserida
✓ Usuário ainda chamado pelo apelido
✓ Dados anteriores consistentes
```

### Teste 5: Edge Cases
```
✓ Áudio → "Não consigo ouvir, digita aí"
✓ Mensagem confusa → pede clareza educadamente
✓ Desistir no meio → reconhece, oferece próximos passos
✓ Erro de save → tenta novamente, avisa se falhar
```

---

## 📞 Suporte/Debug

### Se algo não funciona, verifique:

1. **Usuário não está sendo cadastrado?**
   - Está enviando confirmação explícita?
   - API está aceitando POST /usuarios?

2. **Registro não salva?**
   - Banco recebe confirmação?
   - frente_servico_id é válido?
   - Campos opcionais estão None/null?

3. **Memory não funciona?**
   - Token counter está rodando?
   - Memory block é inserido antes do histórico?
   - Usuário ainda aparece com dados antigos?

4. **Agent não adapta tom?**
   - Memory block preserva estilo?
   - Instrução de adaptação está clara?
   - Temperatura do LLM está apropriada (~0.7)?

---

## 🔗 Documentação Completa

Para detalhes completos, veja:
- **[PROMPT_AGENT_DIARIO.md](./PROMPT_AGENT_DIARIO.md)** — Prompt completo com todos os fluxos
- **[CONTEXTO_E_MEMORIA_AGENTE.md](./CONTEXTO_E_MEMORIA_AGENTE.md)** — Explicação técnica de contexto/memória
- **[MEMORY_PROMPT_AGENTE.md](./MEMORY_PROMPT_AGENTE.md)** — Formato de reinserção de memória

---
