# Agente de Diário de Obra

Repositório backend-only com Flask como servidor principal, além de estrutura base para LangGraph, Telegram, PostgreSQL e Redis.

## Deploy no Google Cloud Run (Docker)

Pré-requisitos:

- Google Cloud SDK (`gcloud`) autenticado.
- Projeto e billing ativos.

Build da imagem com Cloud Build:

```bash
gcloud builds submit --tag gcr.io/SEU_PROJECT_ID/obralog-backend
```

Deploy no Cloud Run:

```bash
gcloud run deploy obralog-backend \
	--image gcr.io/SEU_PROJECT_ID/obralog-backend \
	--platform managed \
	--region southamerica-east1 \
	--allow-unauthenticated \
	--set-env-vars TELEGRAM_POLLING_IN_DEV=false
```

Variáveis recomendadas no serviço:

- `GOOGLE_API_KEY`
- `TELEGRAM_TOKEN`
- `DATABASE_URL`
- `CORS_ORIGINS`
- `AUTH_SECRET_KEY`

Observações:

- O `Dockerfile` inicia com `gunicorn` em `backend.main:app` na porta `PORT` do Cloud Run.
- Em Cloud Run, use webhook do Telegram. Não use polling.

## Telegram

O webhook do Telegram está em `POST /telegram/webhook`. Ele recebe updates do bot, usa `thread_id` por chat para manter o contexto e responde via API do Telegram.

Variáveis mínimas:

- `GOOGLE_API_KEY` para o modelo Gemini.
- `TELEGRAM_TOKEN` para enviar mensagens de volta ao chat.
- `DATABASE_URL` para o checkpointer do LangGraph.

Depois de subir o backend em uma URL pública HTTPS, aponte o webhook do bot para `/telegram/webhook`.
