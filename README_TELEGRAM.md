# Telegram Bot - ObraLog

## Localhost (Desenvolvimento com Polling)

Para testar localmente sem expor o servidor, use polling:

```bash
python backend/agents/telegram_bot.py
```

O bot vai consultar a API do Telegram periodicamente e responder no mesmo terminal onde foi iniciado.

### Variáveis obrigatórias

- `GOOGLE_API_KEY`: Para o modelo Gemini
- `TELEGRAM_TOKEN`: Token do bot obtido em @BotFather no Telegram
- `DATABASE_URL`: Conexão ao Postgres (com checkpointer)

### Fluxo

1. Abra um terminal e rode:
   ```bash
   python backend/agents/telegram_bot.py
   ```

2. Envie uma mensagem para o bot no Telegram.

3. O agente vai responder no contexto do chat (cada chat tem seu `thread_id`).

### Comando para iniciar nova thread

Se quiser zerar o contexto anterior da conversa e começar uma nova thread no mesmo chat, envie:

```text
/nova_thread
```

Comandos equivalentes aceitos: `/novathread`, `/reset_contexto`, `/reset`, `/limpar_contexto`, `/zerar_contexto`.

Observação: isso reinicia apenas o contexto conversacional da IA. Não apaga cadastros nem registros já salvos.

Implementação técnica: o `thread_id` agora é persistido por usuário (`usuarios.telegram_thread_id`).
Com isso, o reset funciona de forma consistente também após restart do processo.

---

## Produção (Webhook)

Para produção com webhook HTTPS:

1. Exponha o servidor em uma URL HTTPS pública.

2. Configure o webhook do bot:
   ```bash
   curl -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/setWebhook?url=https://seu-dominio.com/telegram/webhook"
   ```

3. Suba o backend com o Flask:
   ```bash
   flask run
   ```

O webhook vai estar em `POST /telegram/webhook` recebendo updates.

---

## Instruções do agente em arquivo único

O agente usa um único arquivo como fonte de instruções. Por padrão:

- `backend/agents/context/instructions.txt`

Observação: o prompt base do sistema é fixo, curto e definido no código.
O que o usuário edita via API é somente este arquivo de instruções operacionais.

Você pode trocar o caminho com a variável de ambiente:

- `AGENT_INSTRUCTIONS_FILE`

Exemplo:

```bash
AGENT_INSTRUCTIONS_FILE=backend/agents/context/instructions.txt
```

### Visualizar e editar via API

- `GET /api/v1/agent/instructions` retorna conteúdo atual
- `PUT /api/v1/agent/instructions` atualiza conteúdo

Payload do PUT/PATCH:

```json
{
   "content": "texto completo das instruções"
}
```

Observação: não é necessário banco para isso. O conteúdo fica todo em um único arquivo.
