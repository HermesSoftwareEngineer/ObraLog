# Alterações - 2026-04-05

## Resumo
Refatoração dos modelos de **Frente de Serviço** e **Registros** para melhorar flexibilidade e remover redundâncias, especialmente o campo `hora_registro`.

### Atualização complementar (reset de contexto no Telegram)
- Para garantir que o comando de reset de contexto funcione de forma estável, foi adicionado o campo `telegram_thread_id` em `usuarios`.
- O comando `/nova_thread` agora troca esse `thread_id` persistido, iniciando uma nova thread real no LangGraph.

---

## Endpoint: `POST /api/v1/frentes-servico` (Criar Frente de Serviço)

### ✨ O que mudou

#### Novo campo
- `observacao` (string, opcional): Campo para anotar informações adicionais sobre a frente.

#### Campos obrigatórios
- `nome` (string) ✅

#### Campos opcionais
- `encarregado_responsavel` (integer)
- `observacao` (string)

### 📝 Exemplo de requisição

**Antes (ainda funciona):**
```json
{
  "nome": "Terraplenagem",
  "encarregado_responsavel": 1
}
```

**Agora (com observação):**
```json
{
  "nome": "Terraplenagem",
  "encarregado_responsavel": 1,
  "observacao": "Área próxima ao rio, atentar para chuvas"
}
```

### 📤 Exemplo de resposta (201 Created)

```json
{
  "id": 5,
  "nome": "Terraplenagem",
  "encarregado_responsavel": 1,
  "observacao": "Área próxima ao rio, atentar para chuvas"
}
```

---

## Endpoint: `PUT/PATCH /api/v1/frentes-servico/{frente_id}` (Atualizar Frente)

### ✨ O que mudou

Novo campo disponível para atualização:
- `observacao` (string, opcional)

### 📝 Exemplo de requisição

```json
{
  "observacao": "Situação normalizada, chuvas diminuíram"
}
```

---

## Endpoint: `POST /api/v1/registros` (Criar Registro)

### ⚠️ BREAKING CHANGES

#### ❌ Removido
- `hora_registro` não existe mais
  - **Motivo**: Redundante com `created_at`. O registro sempre carrega a hora de criação automaticamente.
  - **Migração**: Se você estava usando `hora_registro`, use `created_at` da resposta.

#### 🔄 Campos obrigatórios (novo padrão)
- `frente_servico_id` (integer) ✅ — **Agora obrigatório!**

#### 🔄 Campos opcionais
- `data` (string, formato YYYY-MM-DD) — **Agora opcional!**
- `usuario_registrador_id` (integer) — **Agora opcional!**
- `estaca_inicial` (number)
- `estaca_final` (number)
- `resultado` (number)
- `tempo_manha` (string: "limpo", "nublado", "impraticavel")
- `tempo_tarde` (string: "limpo", "nublado", "impraticavel")
- `pista` (string: "direita", "esquerda")
- `lado_pista` (string: "direita", "esquerda")
- `observacao` (string) — **Novo campo!**

### 📝 Exemplos de requisição

**Registro mínimo (apenas frente de serviço):**
```json
{
  "frente_servico_id": 1
}
```

**Registro com dados completos:**
```json
{
  "data": "2026-04-05",
  "frente_servico_id": 1,
  "usuario_registrador_id": 2,
  "estaca_inicial": 10.5,
  "estaca_final": 12.0,
  "tempo_manha": "limpo",
  "tempo_tarde": "nublado",
  "pista": "direita",
  "lado_pista": "direita",
  "observacao": "Trabalho normal, sem intercorrências"
}
```

### 📤 Exemplo de resposta (201 Created)

```json
{
  "id": 42,
  "data": "2026-04-05",
  "frente_servico_id": 1,
  "usuario_registrador_id": 2,
  "estaca_inicial": 10.5,
  "estaca_final": 12.0,
  "resultado": 1.5,
  "tempo_manha": "limpo",
  "tempo_tarde": "nublado",
  "pista": "direita",
  "lado_pista": "direita",
  "observacao": "Trabalho normal, sem intercorrências",
  "created_at": "2026-04-05T08:30:45"
}
```

### ⚠️ Erro ao tentar usar `hora_registro`

```json
{
  "ok": false,
  "error": "Campo obrigatório ausente: frente_servico_id"
}
```

---

## Endpoint: `PUT/PATCH /api/v1/registros/{registro_id}` (Atualizar Registro)

### ✨ O que mudou

#### ❌ Removido
- `hora_registro` não é mais aceito em atualizações

#### ✨ Adicionado
- `observacao` (string, opcional)

#### 🔄 Campos que agora são opcionais em atualizações
- `data`
- `usuario_registrador_id`

### 📝 Exemplo de requisição

```json
{
  "data": "2026-04-06",
  "observacao": "Horário corrigido do dia anterior"
}
```

---

## Modelos de Resposta Atualizados

### FrenteServico

**Antes:**
```json
{
  "id": 1,
  "nome": "string",
  "encarregado_responsavel": 1
}
```

**Agora:**
```json
{
  "id": 1,
  "nome": "string",
  "encarregado_responsavel": 1,
  "observacao": "string|null"
}
```

### Registro

**Antes:**
```json
{
  "id": 1,
  "data": "2026-04-05",
  "hora_registro": "08:30:00",
  "frente_servico_id": 1,
  "usuario_registrador_id": 1,
  "estaca_inicial": 10.5,
  "estaca_final": 12.0,
  "resultado": 1.5,
  "tempo_manha": "limpo",
  "tempo_tarde": "nublado",
  "pista": "direita",
  "lado_pista": "direita",
  "created_at": "2026-04-05T12:00:00"
}
```

**Agora:**
```json
{
  "id": 1,
  "data": "2026-04-05",
  "frente_servico_id": 1,
  "usuario_registrador_id": 1,
  "estaca_inicial": 10.5,
  "estaca_final": 12.0,
  "resultado": 1.5,
  "tempo_manha": "limpo",
  "tempo_tarde": "nublado",
  "pista": "direita",
  "lado_pista": "direita",
  "observacao": "string|null",
  "created_at": "2026-04-05T12:00:00"
}
```

---

## Guia de Migração

### Se você estava usando `hora_registro`

1. **Para criar registros**: Remova `hora_registro` do payload. Ele será capturado automaticamente em `created_at`.

   ```diff
   {
     "data": "2026-04-05",
   - "hora_registro": "08:30:00",
     "frente_servico_id": 1,
     "usuario_registrador_id": 1
   }
   ```

2. **Para ler a hora**: Use `created_at` em vez de `hora_registro`.

   ```diff
   - const hora = registro.hora_registro;
   + const hora = new Date(registro.created_at).toLocaleTimeString();
   ```

### Se você fazia registros com `data` e `usuario_registrador_id` obrigatórios

Agora esses campos são opcionais. Você pode criar registros com apenas `frente_servico_id`:

```json
{
  "frente_servico_id": 1
}
```

---
