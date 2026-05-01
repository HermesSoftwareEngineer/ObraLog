# Mapeamento da API - ObraLog

## Base
- Base URL local: `http://localhost:5000`
- Prefixo REST: `/api/v1`
- Content-Type para escrita: `application/json`
- Autenticação HTTP: Bearer token via header `Authorization: Bearer <token>` (quando aplicável)

## Autenticacao
### POST `/api/v1/auth/register`
- Cria conta de usuário via convite e retorna token.
- O nível de acesso e o tenant são determinados pelo convite.
- Body obrigatório:
```json
{
  "nome": "string",
  "email": "string",
  "senha": "string",
  "invite_code": "ABC123XYZ456"
}
```
- Body opcional:
```json
{
  "telefone": "string"
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
- Erros:
  - `400`: `invite_code` ausente
  - `404`: código de convite inválido
  - `409`: convite já utilizado ou e-mail já cadastrado na unidade
  - `410`: convite expirado

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

### POST `/api/v1/auth/invite-codes`
- Gera convite de cadastro para um novo usuário.
- Apenas administrador ou gerente.
- Convite expira em **24 horas**.
- Header obrigatório:
```text
Authorization: Bearer <token>
```
- Body obrigatório:
```json
{
  "nivel_acesso": "encarregado"
}
```
- Body opcional:
```json
{
  "email_destinatario": "convidado@empresa.com"
}
```
- Resposta 201:
```json
{
  "ok": true,
  "invite": {
    "id": "uuid",
    "codigo": "ABC123XYZ456",
    "email_destinatario": "convidado@empresa.com",
    "nivel_acesso": "encarregado",
    "expira_em": "2026-05-02T12:00:00+00:00",
    "usado_em": null,
    "ativo": true,
    "criado_por": 1,
    "created_at": "2026-05-01T12:00:00+00:00"
  }
}
```

### GET `/api/v1/auth/invite-codes`
- Lista convites ativos (não usados) da unidade do usuário autenticado.
- Apenas administrador ou gerente.
- Header obrigatório:
```text
Authorization: Bearer <token>
```
- Resposta 200: lista de objetos `invite` (mesmo schema acima).

### DELETE `/api/v1/auth/invite-codes/{codigo}`
- Cancela (desativa) um convite pendente.
- Apenas administrador ou gerente.
- Header obrigatório:
```text
Authorization: Bearer <token>
```
- Resposta 200:
```json
{"ok": true}
```

## Unidade

### GET `/api/v1/tenant`
- Retorna todos os dados da unidade (empresa) do usuário autenticado.
- Header obrigatório:
```text
Authorization: Bearer <token>
```
- Resposta 200:
```json
{
  "ok": true,
  "tenant_id": 1,
  "nome": "Construtora XYZ",
  "slug": "construtora-xyz",
  "location_type": "estaca",
  "tipo_negocio": "construção civil",
  "ativo": true,
  "cnpj": "12.345.678/0001-99",
  "razao_social": "Construtora XYZ Ltda",
  "nome_fantasia": "XYZ Obras",
  "logradouro": "Av. Brasil",
  "numero": "1000",
  "complemento": "Sala 201",
  "cep": "01234-567",
  "cidade": "São Paulo",
  "estado": "SP",
  "telefone_comercial": "(11) 3000-0000",
  "email_comercial": "contato@xyz.com.br"
}
```

### PATCH `/api/v1/tenant`
- Atualiza dados da unidade.
- Apenas administrador ou gerente.
- Header obrigatório:
```text
Authorization: Bearer <token>
```
- Body (todos os campos opcionais, enviar apenas os que deseja alterar):
```json
{
  "nome": "string",
  "tipo_negocio": "string",
  "location_type": "estaca | km | text",
  "cnpj": "string",
  "razao_social": "string",
  "nome_fantasia": "string",
  "logradouro": "string",
  "numero": "string",
  "complemento": "string",
  "cep": "string",
  "cidade": "string",
  "estado": "string (2 letras)",
  "telefone_comercial": "string",
  "email_comercial": "string"
}
```
- Resposta 200: mesmo schema do `GET /api/v1/tenant`.

> **Aliases legados** — `GET /api/v1/tenant/config` e `PATCH /api/v1/tenant/config` continuam funcionando e delegam para os endpoints acima.

---

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
  "lado_pista": "esquerdo",
  "pista": "direito",
  "observacao": "Observações do registro",
  "raw_text": "texto bruto da origem",
  "source_message_id": "uuid-opcional"
}
```
- Regra: `observacao` e `lado_pista` são opcionais.
- Regra: `pista` é aceito apenas como alias legado e é normalizado para `lado_pista`.
- Regra: se `resultado` não vier e `estaca_inicial` + `estaca_final` vierem, o backend calcula automaticamente.
- Limite de imagens por registro: `30`.

### GET `/api/v1/registros/{registro_id}`
- Retorna registro por id.

### PUT/PATCH `/api/v1/registros/{registro_id}`
- Atualiza registro.
- Campos aceitos: `data`, `frente_servico_id`, `usuario_registrador_id`, `estaca_inicial`, `estaca_final`, `resultado`, `tempo_manha`, `tempo_tarde`, `lado_pista`, `pista` (alias legado), `observacao`, `raw_text`, `source_message_id`.

## Mensagens de Campo
### GET `/api/v1/mensagens-campo`
- Lista mensagens capturadas no fluxo operacional.
- Header obrigatório:
```text
Authorization: Bearer <token>
```
- Query params opcionais:
  - `status=pendente|processada|erro`
  - `telegram_chat_id=string`
  - `limit=1..200` (default `50`)

### GET `/api/v1/mensagens-campo/{mensagem_id}`
- Retorna detalhe de mensagem de campo por UUID.
- Header obrigatório:
```text
Authorization: Bearer <token>
```

## Chat (Conversas do Agente)
### GET `/api/v1/chat/conversas`
- Lista conversas agrupadas por `telegram_chat_id`.
- Apenas administrador.
- Header obrigatório:
```text
Authorization: Bearer <token>
```
- Query params opcionais:
  - `page=1..N` (default `1`)
  - `per_page=1..200` (default `50`)
- Resposta `200`:
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

### GET `/api/v1/chat/mensagens`
- Lista mensagens de uma conversa específica.
- Apenas administrador.
- Header obrigatório:
```text
Authorization: Bearer <token>
```
- Query params:
  - `chat_id=string` (obrigatório)
  - `page=1..N` (default `1`)
  - `per_page=1..200` (default `50`)
- Resposta `200`:
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
      "direcao": "user",
      "texto": "Conteudo normalizado ou bruto da mensagem",
      "status_processamento": "processada",
      "erro_processamento": null,
      "usuario_id": 7
    }
  ]
}
```
- Regra: `texto` retorna `texto_normalizado` com fallback para `texto_bruto`.
- Regra: `direcao` é `user` (mensagem do usuário) ou `agent` (resposta do agente). Ambas as direções são persistidas.

### GET `/api/v1/chat/conversas/{chat_id}/mensagens`
- Rota legada mantida por compatibilidade.
- Retorna o mesmo payload de `GET /api/v1/chat/mensagens`.

## Fluxo Removido
### `/api/v1/lancamentos/*`
- Todos os endpoints de lançamentos foram removidos do fluxo oficial.
- Resposta atual: `410 Gone` com orientação para usar apenas registros e status de registro.

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
- Resposta `200` (payload de lista simplificado):
```json
{
  "ok": true,
  "total": 1,
  "alertas": [
    {
      "id": "uuid",
      "code": "ALT-2026-0001",
      "type": "maquina_quebrada",
      "severity": "alta",
      "title": "Parada de escavadeira",
      "status": "aberto",
      "is_read": false,
      "reported_at": "2026-04-29T10:00:00+00:00",
      "created_at": "2026-04-29T10:00:00+00:00",
      "location_detail": "km 12",
      "reported_by": 5,
      "reported_by_nome": "Carlos Silva"
    }
  ]
}
```

### POST `/api/v1/alertas`
- Cria alerta operacional.
- Body obrigatório:
```json
{
  "type": "maquina_quebrada",
  "severity": "alta",
  "title": "Parada de escavadeira",
  "reported_at": "2026-04-29T10:00:00-03:00"
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
  "notified_channels": ["telegram", "email"],
  "source": "agent_gateway_tool"
}
```
- Regras:
  - Se `description` não for enviada, o backend gera uma descrição sugerida automaticamente.
  - Em chamadas normais da API, `reported_at` é obrigatório.
  - Em chamadas com `source` de agente (`agent*`, `telegram_agent`, `ia`), `reported_at` pode ser omitido e o backend preenche automaticamente com a data/hora do cadastro.

### GET `/api/v1/alertas/{alert_id}`
- Retorna um alerta por UUID.
- Resposta `200` (payload de detalhe):
```json
{
  "ok": true,
  "alerta": {
    "id": "uuid",
    "code": "ALT-2026-0001",
    "type": "maquina_quebrada",
    "severity": "alta",
    "title": "Parada de escavadeira",
    "status": "em_atendimento",
    "is_read": true,
    "reported_at": "2026-04-29T10:00:00+00:00",
    "created_at": "2026-04-29T10:00:00+00:00",
    "location_detail": "km 12",
    "reported_by": 5,
    "reported_by_nome": "Carlos Silva",
    "description": "Equipamento sem partida",
    "equipment_name": "Escavadeira",
    "photo_urls": ["https://.../foto1.jpg"],
    "priority_score": 90,
    "resolution_notes": null,
    "resolved_by": null,
    "resolved_by_nome": null,
    "resolved_at": null,
    "read_by": 7,
    "read_by_nome": "Ana Souza",
    "read_at": "2026-04-29T10:10:00+00:00",
    "updated_at": "2026-04-29T10:10:00+00:00"
  }
}
```

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
- Resposta: retorna `alerta` no payload de detalhe (inclui `reported_by_nome`, `read_by_nome`, `resolved_by_nome`).

### POST `/api/v1/alertas/{alert_id}/read`
- Marca alerta como lido para o usuário autenticado e registra trilha em `alert_reads`.
- Resposta: retorna `alerta` no payload de detalhe e `leitura` com `worker_nome`.

### POST `/api/v1/alertas/{alert_id}/unread`
- Marca alerta como não lido para o usuário autenticado e remove a trilha de leitura dele em `alert_reads`.
- Resposta: retorna `alerta` no payload de detalhe.

### GET `/api/v1/alertas/tipos/simples`
- Lista tipos de alerta em payload enxuto para o frontend.
- Query params opcionais:
  - `ativos_apenas=true|false` (default `true`)
- Resposta `200`:
```json
{
  "ok": true,
  "total": 2,
  "tipos": [
    {
      "id": "uuid",
      "nome": "pane eletrica",
      "tipo_canonico": "maquina_quebrada",
      "ativo": true
    }
  ]
}
```

### POST `/api/v1/alertas/tipos/simples`
- Cadastra tipo de alerta simplificado.
- Apenas administrador/gerente.
- Body obrigatório:
```json
{
  "nome": "pane eletrica"
}
```
- Body opcional:
```json
{
  "tipo_canonico": "maquina_quebrada",
  "ativo": true
}
```
- Regra: se `tipo_canonico` for omitido, o backend usa `nome` normalizado (ex.: `"pane eletrica"` -> `"pane_eletrica"`).

### PATCH `/api/v1/alertas/tipos/simples/{tipo_id}`
- Atualiza tipo de alerta simplificado.
- Apenas administrador/gerente.
- Body opcional (parcial):
```json
{
  "nome": "pane hidraulica",
  "tipo_canonico": "pane_hidraulica",
  "ativo": true
}
```
- Regra: `tipo_canonico` é opcional também no update.

### DELETE `/api/v1/alertas/tipos/simples/{tipo_id}`
- Remove tipo de alerta simplificado.
- Apenas administrador/gerente.

## Dashboard

Todos os endpoints de dashboard exigem `Authorization: Bearer <token>`.

### GET `/api/v1/dashboard/overview`
- Painel principal com KPIs globais + séries temporais.
- Query params opcionais:
  - `days` (int, 7–365, default `30`) — janela das séries temporais
  - `obra_id` (int) — filtra métricas por obra
- Resposta 200:
```json
{
  "ok": true,
  "periodo": { "inicio": "2026-04-01", "fim": "2026-04-30", "days": 30 },
  "kpis": {
    "usuarios_total": 12,
    "frentes_total": 5,
    "obras_ativas": 3,
    "registros_total": 320,
    "progresso_total": 980.5,
    "alertas_abertos": 4,
    "alertas_criticos": 1,
    "alertas_nao_lidos": 2,
    "registros_periodo": 87,
    "progresso_periodo": 210.75,
    "dias_impraticaveis_periodo": 3,
    "mensagens_agente_periodo": 142
  },
  "charts": {
    "serie_diaria": [
      {
        "date": "2026-04-01",
        "registros": 4,
        "progresso": 12.5,
        "impraticaveis_manha": 0,
        "impraticaveis_tarde": 1
      }
    ],
    "progresso_por_frente": [
      { "frente_id": 1, "frente_nome": "Terraplenagem", "total_registros": 30, "progresso": 120.0 }
    ],
    "alertas_por_severidade": { "critica": 1, "alta": 3, "media": 5, "baixa": 2 },
    "alertas_por_status": { "aberto": 4, "resolvido": 7, "cancelado": 1 },
    "alertas_por_dia": [
      { "date": "2026-04-10", "total": 2 }
    ],
    "top_encarregados": [
      { "usuario_id": 3, "usuario_nome": "Carlos", "total_registros": 12, "progresso": 48.0 }
    ]
  }
}
```

### GET `/api/v1/dashboard/producao`
- Análise detalhada de produção com progresso acumulado e breakdown climático.
- Query params:
  - `data_inicio` (YYYY-MM-DD, **obrigatório**)
  - `data_fim`    (YYYY-MM-DD, **obrigatório**)
  - `frente_id`   (int, opcional)
  - `obra_id`     (int, opcional)
- Período máximo: 365 dias.
- Resposta 200:
```json
{
  "ok": true,
  "periodo": { "inicio": "2026-04-01", "fim": "2026-04-30" },
  "resumo": {
    "total_registros": 87,
    "progresso_total": 210.75,
    "dias_trabalhados": 22,
    "dias_impraticaveis": 3,
    "frentes_ativas": 4,
    "encarregados_ativos": 6,
    "media_diaria": 9.58
  },
  "charts": {
    "progresso_acumulado": [
      { "date": "2026-04-01", "progresso_dia": 8.5, "progresso_acumulado": 8.5 },
      { "date": "2026-04-02", "progresso_dia": 10.0, "progresso_acumulado": 18.5 }
    ],
    "por_frente": [
      {
        "frente_id": 1,
        "frente_nome": "Terraplenagem",
        "registros": 30,
        "progresso": 120.0,
        "dias_ativos": 18,
        "media_diaria": 6.67
      }
    ],
    "clima_manha": { "limpo": 60, "nublado": 20, "impraticavel": 7 },
    "clima_tarde":  { "limpo": 55, "nublado": 25, "impraticavel": 7 },
    "por_pista": [
      { "lado": "direito", "registros": 45, "progresso": 130.5 },
      { "lado": "esquerdo", "registros": 42, "progresso": 80.25 }
    ]
  }
}
```
- Erros:
  - `400`: parâmetros ausentes, datas inválidas ou período > 365 dias

### GET `/api/v1/dashboard/alertas`
- Análise de alertas operacionais: taxa de resolução, tempo médio, série diária.
- Query params opcionais:
  - `days`    (int, 7–365, default `30`)
  - `obra_id` (int)
- Resposta 200:
```json
{
  "ok": true,
  "periodo": { "inicio": "2026-04-01", "fim": "2026-04-30", "days": 30 },
  "kpis": {
    "total_periodo": 11,
    "resolvidos_periodo": 7,
    "taxa_resolucao_pct": 63.6,
    "tempo_medio_resolucao_horas": 4.2,
    "abertos_criticos_atual": 1
  },
  "charts": {
    "por_severidade": { "critica": 1, "alta": 3, "media": 5, "baixa": 2 },
    "por_tipo": [
      { "tipo": "maquina_quebrada", "total": 5 }
    ],
    "por_status_snapshot": { "aberto": 4, "resolvido": 7, "cancelado": 1 },
    "serie_diaria": [
      { "date": "2026-04-10", "total": 2, "resolvidos": 1 }
    ]
  }
}
```

### GET `/api/v1/dashboard/equipe`
- Métricas de equipe: headcount, ranking de produtividade por encarregado, atividade por dia da semana.
- Query params opcionais:
  - `days` (int, 7–365, default `30`)
- Resposta 200:
```json
{
  "ok": true,
  "periodo": { "inicio": "2026-04-01", "fim": "2026-04-30", "days": 30 },
  "kpis": {
    "total_usuarios": 12,
    "com_telegram_vinculado": 9,
    "pct_telegram_vinculado": 75.0,
    "por_nivel": { "administrador": 1, "gerente": 2, "encarregado": 9 }
  },
  "charts": {
    "ranking_encarregados": [
      {
        "usuario_id": 3,
        "nome": "Carlos Silva",
        "nivel": "encarregado",
        "registros": 12,
        "progresso": 48.0,
        "dias_ativos": 10,
        "telegram_vinculado": true
      }
    ],
    "atividade_por_dia_semana": [
      { "dow": 1, "nome": "Seg", "registros": 18, "progresso": 54.0 },
      { "dow": 6, "nome": "Sáb", "registros": 3, "progresso": 8.0 }
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

### Últimas Alterações (2026-05-01)
- ✅ **Dashboard profissional**: 4 endpoints analíticos em `/api/v1/dashboard/` — `overview`, `producao`, `alertas` e `equipe`. KPIs, séries temporais, rankings, breakdown climático e análise de alertas.
- ✅ **Unidade (Tenant)**: novos endpoints `GET /api/v1/tenant` e `PATCH /api/v1/tenant` com campos completos de empresa (CNPJ, endereço, etc.). Aliases `/tenant/config` mantidos.
- ✅ **Convites de cadastro**: `POST /api/v1/auth/invite-codes`, `GET /api/v1/auth/invite-codes`, `DELETE /api/v1/auth/invite-codes/{codigo}`. Requer admin ou gerente. Convites expiram em 24 h.
- 🔄 **`POST /api/v1/auth/register`**: agora exige `invite_code` no body. O tenant e o nível de acesso são determinados pelo convite. Registro livre foi removido.
- ✅ **Multi-tenant**: todos os repositórios e rotas operam com isolamento por `tenant_id` extraído do JWT.
- ✅ **Obras**: CRUD completo em `/api/v1/obras`; `obra_id` disponível em registros e alertas.

[Veja detalhes completos →](./docs/api-changes/20260501_022_unidade_invite_codes.md)
