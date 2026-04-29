# Alteracoes de API - 2026-04-29

## Resumo

Simplificacao dos contratos de resposta de Alertas para reduzir payload no frontend e tornar os campos de usuario mais legiveis.

## Endpoints afetados

- `GET /api/v1/alertas`
- `GET /api/v1/alertas/{alert_id}`
- `POST /api/v1/alertas`
- `PATCH /api/v1/alertas/{alert_id}/status`
- `POST /api/v1/alertas/{alert_id}/read`
- `POST /api/v1/alertas/{alert_id}/unread`
- `GET /api/v1/alertas/codigo/{code}`

## O que mudou

### 0) Data/hora do reporte no cadastro
No cadastro de alerta (`POST /api/v1/alertas`):

- `reported_at` passou a ser obrigatório para chamadas normais da API.
- Se a origem for agente (`source` iniciado por `agent`, ou `telegram_agent`, `ia`), `reported_at` pode ser omitido e o backend define automaticamente com a data/hora do cadastro.
- O campo `reported_at` passou a ser retornado nos payloads de alerta.

### 0.1) Endpoints simples para tipos de alerta
Foram adicionados endpoints simplificados de tipos para o frontend:

- `GET /api/v1/alertas/tipos/simples`
- `POST /api/v1/alertas/tipos/simples`
- `PATCH /api/v1/alertas/tipos/simples/{tipo_id}`
- `DELETE /api/v1/alertas/tipos/simples/{tipo_id}`

Contrato simplificado de retorno:

- `id`
- `nome`
- `tipo_canonico`
- `ativo`

### 1) Payload de lista simplificado
`GET /api/v1/alertas` passa a retornar apenas campos de listagem:

- `id`
- `code`
- `type`
- `severity`
- `title`
- `status`
- `is_read`
- `reported_at`
- `created_at`
- `location_detail`
- `reported_by`
- `reported_by_nome`

### 2) Payload de detalhe consolidado
Endpoints de detalhe/retorno de alerta passam a usar payload de detalhe padronizado com:

- Base da listagem
- `description`
- `equipment_name`
- `photo_urls`
- `priority_score`
- `resolution_notes`
- `resolved_by`
- `resolved_by_nome`
- `resolved_at`
- `read_by`
- `read_by_nome`
- `read_at`
- `updated_at`

### 3) Campos de usuario com nome
Sempre que houver id de usuario no payload de alerta, agora a API retorna tambem o nome correspondente:

- `reported_by` + `reported_by_nome`
- `read_by` + `read_by_nome`
- `resolved_by` + `resolved_by_nome`

No endpoint de leitura:

- `leitura.worker_id` + `leitura.worker_nome`

## Compatibilidade

- Mudanca de contrato de resposta em `GET /api/v1/alertas` (payload menor).
- Clientes que consumiam campos tecnicos extras na listagem devem migrar para:
  - `GET /api/v1/alertas/{alert_id}` (detalhe), ou
  - ajustar para os campos novos de listagem.

## Guia rapido de migracao (frontend)

1. Atualizar tipagem de lista para o payload simplificado.
2. Usar `*_nome` para exibir responsavel/leitura/resolucao em UI.
3. Quando precisar de informacao ampliada, buscar detalhe por id.
