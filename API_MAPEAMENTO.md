# Mapeamento da API - ObraLog

## Base
- Base URL local: `http://localhost:5000`
- Prefixo REST: `/api/v1`
- Content-Type para escrita: `application/json`
- Autenticação HTTP: Bearer token via header `Authorization: Bearer <token>` (quando aplicável)

## Autenticacao
### POST `/api/v1/auth/register`
- Cria conta de usuário (nível inicial `encarregado`) e retorna token.
- Body obrigatório:
```json
{
  "nome": "string",
  "email": "string",
  "senha": "string",
  "telefone": "string (opcional)"
}
```
- Resposta 201:
```json
{
  "ok": true,
  "token": "string",
  "user": {
    "id": 1,
    "nome": "string",
    "email": "string",
    "telefone": "string|null",
    "telegram_chat_id": null,
    "nivel_acesso": "encarregado"
  }
}
```

### POST `/api/v1/auth/login`
- Autentica usuário e retorna token.
- Body obrigatório:
```json
{
  "email": "string",
  "senha": "string"
}
```
- Resposta 200:
```json
{
  "ok": true,
  "token": "string",
  "user": {
    "id": 1,
    "nome": "string",
    "email": "string",
    "telefone": "string|null",
    "telegram_chat_id": "string|null",
    "nivel_acesso": "administrador|gerente|encarregado"
  }
}
```

### GET `/api/v1/auth/me`
- Retorna dados do usuário autenticado.
- Header obrigatório:
```text
Authorization: Bearer <token>
```
- Resposta 200:
```json
{
  "ok": true,
  "user": {
    "id": 1,
    "nome": "string",
    "email": "string",
    "telefone": "string|null",
    "telegram_chat_id": "string|null",
    "nivel_acesso": "administrador|gerente|encarregado"
  }
}
```

### PATCH `/api/v1/auth/link-telegram`
- Vincula `telegram_chat_id` ao usuário autenticado.
- Header obrigatório:
```text
Authorization: Bearer <token>
```
- Body obrigatório:
```json
{
  "telegram_chat_id": "1751541108"
}
```

### POST `/api/v1/auth/telegram-link-codes`
- Gera código de vínculo de Telegram para qualquer usuário.
- Apenas administrador.
- O código não expira por tempo.
- O código é invalidado quando o telefone do usuário alvo é alterado.
- Header obrigatório:
```text
Authorization: Bearer <token>
```
- Body obrigatório:
```json
{
  "user_id": 12
}
```
- Resposta 201:
```json
{
  "ok": true,
  "link_code": {
    "code": "AB12CD34",
    "user_id": 12,
    "expires_at": "9999-12-31T23:59:59",
    "generated_by_user_id": 1
  }
}
```
- Resposta 200:
```json
{
  "ok": true,
  "user": {
    "id": 1,
    "nome": "string",
    "email": "string",
    "telefone": "string|null",
    "telegram_chat_id": "1751541108",
    "nivel_acesso": "administrador"
  }
}
```

## Healthcheck
### GET `/health`
- Resposta 200:
```json
{"status":"ok"}
```

### GET `/`
- Resposta 200:
```json
{"message":"Agente de Diário de Obra backend ativo"}
```

## Usuarios
### GET `/api/v1/usuarios`
- Lista todos os usuários.

### POST `/api/v1/usuarios`
- Cria usuário.
- Body obrigatório:
```json
{
  "nome": "string",
  "email": "string",
  "senha": "string",
  "telefone": "string (opcional)"
}
```
- Body opcional:
```json
{
  "nivel_acesso": "administrador | gerente | encarregado",
  "telefone": "string",
  "telegram_chat_id": "string"
}
```

### GET `/api/v1/usuarios/{usuario_id}`
- Retorna usuário por id.

### PUT/PATCH `/api/v1/usuarios/{usuario_id}`
- Atualiza usuário.
- Campos aceitos: `nome`, `email`, `senha`, `telefone`, `nivel_acesso`, `telegram_chat_id`.

### DELETE `/api/v1/usuarios/{usuario_id}`
- Remove usuário.

## Frentes de Servico
### GET `/api/v1/frentes-servico`
- Lista frentes de serviço.

### POST `/api/v1/frentes-servico`
- Cria frente de serviço.
- Body obrigatório:
```json
{
  "nome": "Terraplenagem"
}
```
- Body opcional:
```json
{
  "encarregado_responsavel": 1,
  "observacao": "Observações sobre a frente"
}
```

### GET `/api/v1/frentes-servico/{frente_id}`
- Retorna frente por id.

### PUT/PATCH `/api/v1/frentes-servico/{frente_id}`
- Atualiza frente.
- Campos aceitos: `nome`, `encarregado_responsavel`, `observacao`.

### DELETE `/api/v1/frentes-servico/{frente_id}`
- Remove frente.

## Registros
### GET `/api/v1/registros`
- Lista registros.
- Query params opcionais:
  - `data=YYYY-MM-DD`
  - `frente_servico_id=number`
  - `usuario_id=number`

### POST `/api/v1/registros`
- Cria registro.
- Body obrigatório:
```json
{
  "frente_servico_id": 1,
  "data": "2026-04-05",
  "usuario_registrador_id": 1,
  "estaca_inicial": 10.5,
  "estaca_final": 12.0,
  "tempo_manha": "limpo",
  "tempo_tarde": "nublado"
}
```
- Body opcional:
```json
{
  "resultado": 1.5,
  "pista": "direito",
  "lado_pista": "esquerdo",
  "observacao": "Observações do registro"
}
```
- Regra: `observacao`, `pista` e `lado_pista` são opcionais.
- Regra: se `resultado` não vier e `estaca_inicial` + `estaca_final` vierem, o backend calcula automaticamente.
- Limite de imagens por registro: `30`.

### GET `/api/v1/registros/{registro_id}`
- Retorna registro por id.

### PUT/PATCH `/api/v1/registros/{registro_id}`
- Atualiza registro.
- Campos aceitos: `data`, `frente_servico_id`, `usuario_registrador_id`, `estaca_inicial`, `estaca_final`, `resultado`, `tempo_manha`, `tempo_tarde`, `pista`, `lado_pista`, `observacao`.

### GET `/api/v1/registros/{registro_id}/imagens`
- Lista imagens vinculadas ao registro.

### POST `/api/v1/registros/{registro_id}/imagens`
- Faz upload de uma imagem para o registro.
- `Content-Type`: `multipart/form-data`
- Campo obrigatório no form-data: `imagem`
- Tipos permitidos: `image/jpeg`, `image/png`, `image/webp`, `image/heic`, `image/heif`
- Respostas relevantes:
  - `201`: imagem anexada
  - `404`: registro não encontrado
  - `409`: limite de 30 imagens atingido

### DELETE `/api/v1/registros/{registro_id}/imagens/{imagem_id}`
- Remove imagem vinculada ao registro.

### GET `/backend/uploads/registros/{filename}`
- Retorna arquivo de imagem salvo localmente para exibição/download no frontend.
- Exemplo:
```text
http://localhost:5000/backend/uploads/registros/registro_5_abc123.jpg
```

### GET `/api/v1/backend/uploads/registros/{filename}`
- Rota compatível adicional para leitura de imagens de registros.
- Exemplo:
```text
http://localhost:5000/api/v1/backend/uploads/registros/registro_5_abc123.jpg
```

### DELETE `/api/v1/registros/{registro_id}`
- Remove registro.

## Diário de Obra
### GET `/api/v1/diario/dia`
- Retorna diário consolidado de um dia.
- Query params:
  - `data=YYYY-MM-DD` (obrigatório)
  - `frente_servico_id=number` (opcional)
- Respostas relevantes:
  - `200`: diário retornado com totais por dia
  - `404`: nenhum registro para os filtros
  - `422`: parâmetros inválidos

### GET `/api/v1/diario/periodo`
- Retorna relatório consolidado por período, agrupado por dia.
- Query params:
  - `data_inicio=YYYY-MM-DD` (obrigatório)
  - `data_fim=YYYY-MM-DD` (obrigatório)
  - `frente_servico_id=number` (opcional)
  - `usuario_id=number` (opcional)
  - `apenas_impraticaveis=true|false` (opcional, default `false`)
- Regras:
  - `data_fim` não pode ser anterior a `data_inicio`
  - período máximo de 365 dias

### GET `/api/v1/diario/exportar`
- Retorna o mesmo payload do endpoint de período em JSON para exportação.
- Query params: mesmos do `/api/v1/diario/periodo`
- Header de resposta:
```text
Content-Disposition: inline; filename="diario_YYYYMMDD_YYYYMMDD.json"
```

### GET `/api/v1/diario/frentes`
- Lista frentes disponíveis para filtros do diário.

## Alertas
### GET `/api/v1/alertas`
- Lista alertas operacionais.
- Query params opcionais:
  - `status=aberto|em_atendimento|aguardando_peca|resolvido|cancelado`
  - `severity=baixa|media|alta|critica`
  - `apenas_nao_lidos=true|false`

### POST `/api/v1/alertas`
- Cria alerta operacional.
- Body obrigatório:
```json
{
  "type": "maquina_quebrada",
  "severity": "alta",
  "title": "Parada de escavadeira"
}
```
- Body opcional:
```json
{
  "description": "Equipamento sem partida",
  "telegram_message_id": 123456,
  "raw_text": "texto original",
  "location_detail": "km 12",
  "equipment_name": "Escavadeira",
  "photo_urls": ["https://.../foto1.jpg"],
  "priority_score": 90,
  "notified_channels": ["telegram", "email"]
}
```
- Regra: se `description` não for enviada, o backend gera uma descrição sugerida automaticamente.

### GET `/api/v1/alertas/{alert_id}`
- Retorna um alerta por UUID.

### PATCH `/api/v1/alertas/{alert_id}/status`
- Atualiza status do alerta.
- Apenas administrador/gerente.
- Body obrigatório:
```json
{
  "status": "resolvido"
}
```
- Body opcional:
```json
{
  "resolution_notes": "Troca de peça concluída"
}
```

### POST `/api/v1/alertas/{alert_id}/read`
- Marca alerta como lido para o usuário autenticado e registra trilha em `alert_reads`.

## Dashboard
### GET `/api/v1/dashboard/overview`
- Retorna KPIs e séries básicas para gráficos.
- Exemplo de resposta:
```json
{
  "kpis": {
    "usuarios_total": 10,
    "frentes_servico_total": 4,
    "registros_total": 120,
    "progresso_total": 350.75
  },
  "charts": {
    "registros_por_dia_7d": [
      {"date": "2026-03-30", "total": 4},
      {"date": "2026-03-31", "total": 7}
    ],
    "progresso_por_dia_7d": [
      {"date": "2026-03-30", "resultado_total": 14.5},
      {"date": "2026-03-31", "resultado_total": 22.0}
    ],
    "progresso_por_frente": [
      {"frente_servico_id": 1, "resultado_total": 120.0},
      {"frente_servico_id": 2, "resultado_total": 90.25}
    ]
  }
}
```

## Configuracao do Agente
### GET `/api/v1/agent/instructions`
- Retorna o conteúdo do arquivo único de instruções do agente.
- Apenas administrador.
- Header obrigatório:
```text
Authorization: Bearer <token>
```
- Resposta 200:
```json
{
  "ok": true,
  "path": "backend/agents/context/instructions.txt",
  "content": "texto completo das instruções",
  "exists": true
}
```

### PUT/PATCH `/api/v1/agent/instructions`
- Atualiza o conteúdo do arquivo único de instruções do agente.
- Apenas administrador.
- Header obrigatório:
```text
Authorization: Bearer <token>
```
- Body obrigatório:
```json
{
  "content": "texto completo das instruções"
}
```
- Resposta 200:
```json
{
  "ok": true,
  "path": "backend/agents/context/instructions.txt",
  "content": "texto completo das instruções"
}
```

## Webhook Telegram
### POST `/telegram/webhook`
- Endpoint de integração do bot Telegram.
- Não é endpoint de uso direto pelo frontend web.
- `telegram_chat_id` é capturado automaticamente a partir do update do Telegram.
- Se o usuário ainda não existir, o bot orienta solicitar código de vínculo ao administrador.
- Fluxo de vínculo por código:
  - Admin gera código em `POST /api/v1/auth/telegram-link-codes`.
  - Usuário envia no Telegram: `/vincular CODIGO`.
  - Código não expira por tempo.
  - Se o telefone do usuário for alterado, os códigos pendentes dele são invalidados.
  - Bot valida código, vincula `telegram_chat_id` automaticamente e marca código como usado.

## Modelos de resposta (resumo)
### Usuario
```json
{
  "id": 1,
  "nome": "string",
  "email": "string",
  "telefone": "string|null",
  "telegram_chat_id": "string|null",
  "nivel_acesso": "administrador|gerente|encarregado",
  "created_at": "2026-04-05T12:00:00"
}
```

### FrenteServico
```json
{
  "id": 1,
  "nome": "string",
  "encarregado_responsavel": 1,
  "observacao": "string|null"
}
```

### Registro
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
  "pista": "direito",
  "lado_pista": "direito",
  "observacao": "string|null",
  "created_at": "2026-04-05T12:00:00"
}
```

## Erros padrao
- Formato de erro:
```json
{"ok": false, "error": "mensagem"}
```
- Códigos comuns: `400`, `404`, `500`.

## 📚 Documentação de Alterações

Para acompanhar as mudanças realizadas na API, consulte:
- **[CHANGELOG.md](./CHANGELOG.md)** - Resumo de todas as alterações por data
- **[docs/api-changes/](./docs/api-changes/)** - Documentação detalhada de cada alteração com guias de migração

### Últimas Alterações (2026-04-07)
- ✨ Campo `observacao` adicionado em Frentes de Serviço e Registros
- 🔄 `frente_servico_id` agora obrigatório em Registros
- ❌ Campo `hora_registro` removido de Registros
- ✅ Campo `observacao` agora opcional em Registros
- ✅ Rotas de download de imagem disponíveis em `/backend/uploads/registros/{filename}` e `/api/v1/backend/uploads/registros/{filename}`
- ✅ Endpoints de Diário de Obra adicionados em `/api/v1/diario/*`
- ✅ Endpoints de Alertas adicionados em `/api/v1/alertas/*`
- ✅ Campos legados removidos da tabela e contratos de Alertas

[Veja detalhes completos →](./docs/api-changes/20260405_alteracoes_frente_registros.md)
