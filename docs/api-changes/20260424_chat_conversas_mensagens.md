# Alteracoes de API - 2026-04-24

## Resumo

Novos endpoints para visualizacao das conversas do agente com os usuarios via Telegram.
Acesso restrito a `administrador`.

## Novos Endpoints

- `GET /api/v1/chat/conversas`
- `GET /api/v1/chat/conversas/{chat_id}/mensagens`

---

## Regras de Permissao

- Ambos os endpoints exigem `Authorization: Bearer <token>`.
- Somente usuarios com `nivel_acesso = administrador` podem acessar. Outros recebem `403 Forbidden`.

---

## GET /api/v1/chat/conversas

Lista todas as conversas agrupadas por `telegram_chat_id`.

### Query params

| Param | Tipo | Default | Descricao |
|-------|------|---------|-----------|
| `page` | int | 1 | Pagina atual |
| `per_page` | int | 50 | Itens por pagina (max 200) |

### Response `200`

```json
{
  "ok": true,
  "page": 1,
  "per_page": 50,
  "total": 12,
  "conversas": [
    {
      "telegram_chat_id": "123456789",
      "total_mensagens": 34,
      "ultima_mensagem_em": "2026-04-24T14:30:00+00:00",
      "ultima_mensagem_texto": "Texto da última mensagem recebida",
      "usuario": {
        "id": 7,
        "nome": "João Encarregado",
        "nivel_acesso": "encarregado"
      }
    }
  ]
}
```

**Notas:**
- `usuario` e `null` quando o `telegram_chat_id` nao esta vinculado a nenhum usuario cadastrado.
- Ordenado por `ultima_mensagem_em` decrescente (conversas mais recentes primeiro).
- Inclui apenas chats com `telegram_chat_id` preenchido.

---

## GET /api/v1/chat/conversas/{chat_id}/mensagens

Lista as mensagens recebidas de um chat especifico.

### Path param

| Param | Tipo | Descricao |
|-------|------|-----------|
| `chat_id` | string | `telegram_chat_id` da conversa |

### Query params

| Param | Tipo | Default | Descricao |
|-------|------|---------|-----------|
| `page` | int | 1 | Pagina atual |
| `per_page` | int | 50 | Itens por pagina (max 200) |

### Response `200`

```json
{
  "ok": true,
  "telegram_chat_id": "123456789",
  "page": 1,
  "per_page": 50,
  "total": 34,
  "mensagens": [
    {
      "id": "uuid-da-mensagem",
      "canal": "telegram",
      "telegram_message_id": 98,
      "recebida_em": "2026-04-24T14:30:00+00:00",
      "tipo_conteudo": "texto",
      "texto": "Conteudo normalizado ou bruto da mensagem",
      "status_processamento": "processada",
      "erro_processamento": null,
      "usuario_id": 7
    }
  ]
}
```

**Notas:**
- Ordenado por `recebida_em` decrescente (mensagens mais recentes primeiro).
- `texto` retorna `texto_normalizado` com fallback para `texto_bruto`.
- `tipo_conteudo`: `texto | foto | audio | misto`.
- `status_processamento`: `pendente | processada | erro`.
- Somente mensagens dos **usuarios** sao armazenadas. As respostas do agente nao sao persistidas no banco.

---

## Respostas de Erro

| Status | Descricao |
|--------|-----------|
| `401` | Token ausente, invalido ou expirado |
| `403` | Usuario nao e administrador |
