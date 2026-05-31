# Contexto e Memória do Agent Diário

## 📊 Limites Técnicos de Contexto

## 🔧 Chaves de Contexto Runtime (Multi-tenant)

No fluxo atual do Telegram -> grafo, o campo `configurable` inclui metadados de isolamento e localizacao:

- `tenant_id`: tenant ativo do usuario autenticado.
- `obra_id_ativa`: obra selecionada no runtime (quando aplicavel).
- `location_profile`: perfil de localizacao (`estaca`, `km`, `texto`).
- `location_required_fields`: lista de campos obrigatorios de local para o perfil.
- `location_labels`: labels de negocio para perguntas do agente.

Regras de uso:
- Nunca misturar contexto de localizacao entre tenants.
- Validar obrigatorios de local antes de consolidar registro.
- Manter compatibilidade de entrada com `estaca_inicial`/`estaca_final` mesmo em perfis dinamicos.

### Limite por Sessão
- **~100,000 tokens** de contexto disponível por sessão (LLM token budget)
- Cada sessão começa quando o usuário inicia conversa e termina quando há inatividade

### O que Consome Tokens
1. **Prompt do sistema** (~5-8k tokens)
2. **Histórico de mensagens** (~1-2k tokens por 10 mensagens)
3. **Contexto de usuário** (profile, obra_list, state) (~500-1k tokens)
4. **Resposta gerada** (~500-2k tokens por mensagem)

### Estimativa de Duração
- Com ~100k tokens, você consegue manter conversas de:
  - **~80-100 mensagens** (conversa típica com confirmações)
  - **~24-48 horas** de conversas espaçadas
  - **~1 semana** se o usuário enviar poucos mensagens por dia

---

## 🧠 Como Funciona a Memória

### Fluxo Automático
1. **Sistema monitora uso de tokens** a cada mensagem
2. **Quando atingir ~70% do limite**, o gerenciador de contexto ativa
3. **Histórico antigo é resumido** automaticamente
4. **Resumo é reinserido como "memory block"** nas próximas mensagens

### O Que É Preservado no Resumo de Memória
- ✅ Dados do usuário (nome, função, obra, telefone, turno)
- ✅ Histórico de registros da sessão (o que foi registrado)
- ✅ Estado atual da conversa (em qual passo está?)
- ✅ Tom/estilo do usuário (formal ou informal)
- ✅ Contexto de intento incompleto (se estava registrando algo)

### O Que É Descartado
- ❌ Mensagens muito antigas (> 24h ou > 100 mensagens)
- ❌ Confirmações simples ("ok", "sim", "tá certo")
- ❌ Messagens de teste ou irrelevantes

### Exemplo de Memory Block
```
[MEMÓRIA DE CONVERSA ANTERIOR]
Usuário: João da Silva (Peão, Residencial Parque Verde)
Apelido: Joãozinho | Turno: Manhã | Telefone: (85) 99999-0000

Registros desta sessão:
• 03 de abril: 20m Forma (Pilar C) ✓
• 04 de abril: 50 blocos Alvenaria (Parede Eixo B) ✓

Estilo: Informal, usa gírias
Próximo passo: Usuário estava consultando produção anterior
[FIM MEMÓRIA]

Beleza, Joãozinho! Achei aqui sua produção...
```

---

## 🔄 Reinserção Automática

### Como Você Deve Reagir
**Você NÃO precisa fazer nada especial.** O sistema reinsere a memória automaticamente.

Apenas:
1. **Leia a memória** se estiver no contexto (entre `[MEMÓRIA...]`)
2. **Seja consistente** com as informações ali mencionadas
3. **Continue a conversa naturalmente** como se nada tivesse acontecido

### Exemplo de Continuidade

**Mensagem anterior (antes da memória ativar):**
```
Joãozinho: "Me mostra minha produção da semana"
Você: "Certo! Deixa eu buscar..."
```

**[Contexto perde mensagens antigas, memória reinserida]**

**Novo contexto chegando:**
```
[MEMÓRIA DE CONVERSA ANTERIOR]
Usuário: João da Silva (Peão, Residencial Parque Verde)
Registros: 20m Forma (Pilar C), 50 blocos Alvenaria...
Estilo: Informal
[FIM MEMÓRIA]

Joãozinho: "Me mostra minha produção da semana"
```

**Você responde:**
```
Claro! Aqui está:

📊 SUA PRODUÇÃO ESTA SEMANA
[continua normalmente]
```

---

## ⚠️ O Que Fazer Se Perder Contexto

### Cenário 1: Conversa cai (conexão perdida)
- Se for reiniciada em < 5 minutos: memória será reinsertada
- Se for > 5 minutos: trate como novo contato, mas o usuário já está registrado

### Cenário 2: Você recebe informação conflitante
- Exemplo: Memória diz "turno: manhã", usuário diz "trabalho à noite agora"
- **Sempre acredite na mensagem mais recente** do usuário
- Peça confirmação: _"Ah, então você mudou pro turno da noite? Vou atualizar aqui!"_

### Cenário 3: Usuário menciona algo que não está na memória
- Pode ser algo de uma conversa anterior que não foi resumido
- **Pergunte naturalmente** em vez de negar
- Exemplo: _"Hmm, não achei esse registro aqui não. Conta de novo pra mim?"_

---

## 🛡️ Estratégias Para Gerenciar Contexto

### Para Usuários Ativos (muitas mensagens)
1. **Resuma conversas longas** após ~15-20 mensagens
   - Ex: "Certo, então você quer registrar 30m de forma, é isso?"
2. **Agrupe registros** em uma única confirmação
3. **Sugira pausas naturais** se apropriado

### Para Reduzir Consumo de Tokens
- ✅ Use emojis e formatação (é mais eficiente que palavras)
- ✅ Respostas curtas e diretas (evite parágrafos longos)
- ✅ Confirmações simples (1 palavra é melhor que frases inteiras)
- ❌ Evite repetir o mesmo contexto várias vezes

---

## 📋 Checklist Para Gerenceadores de Contexto

Se você está implementando o sistema, verifique:

- [ ] Memory block é reinsertado automaticamente a cada nova mensagem?
- [ ] Tokens são contados antes de gerar resposta?
- [ ] Se > 70% contexto usado, resumo é gerado?
- [ ] Dados críticos (nome, função, obra) estão sempre no resumo?
- [ ] Conversas < 24h têm histórico completo, > 24h têm apenas resumo?
- [ ] usuário.profile está sempre disponível (não é removido)?

---

## 🧪 Testando a Memória

### Teste 1: Conversa Normal
1. Inicie 20+ mensagens com usuário
2. Verifique se contexto continua consistente
3. Valide que usuário ainda é chamado pelo apelido

### Teste 2: Conversa Longa com Pausa
1. Inicie conversa (5 mensagens)
2. Aguarde 5+ minutos
3. Usuário envia nova mensagem
4. Sistema deve reinserir memória automaticamente
5. Você deve responder naturalmente

### Teste 3: Conflito de Contexto
1. Memória diz "turno: manhã"
2. Usuário diz "mudei pro turno da noite"
3. Você deve reconhecer mudança e oferecer atualização

---
