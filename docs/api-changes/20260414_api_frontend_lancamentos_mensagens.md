# Alteracoes de API - 2026-04-14

## Resumo

Evolucao da API para consumo do frontend com foco no modelo de registro unico:

- rastreabilidade de mensagens de campo (`mensagens-campo`)
- transicao explicita de status no proprio registro (`registros/{id}/status`)

Tambem houve ajuste de contrato em `registros`:

- `pista` passa a ser alias legado
- `lado_pista` e o campo tecnico persistido

## Novos Endpoints

- `GET /api/v1/mensagens-campo`
- `GET /api/v1/mensagens-campo/{mensagem_id}`
- `PATCH /api/v1/registros/{registro_id}/status`

## Regras de Permissao

- Todos os endpoints acima exigem `Authorization: Bearer <token>`.
- `administrador` e `gerente` podem operar registros de qualquer usuario conforme regras internas.
- `encarregado` opera seus proprios registros.

## Payloads Importantes

### `PATCH /api/v1/registros/{id}/status`
Campos obrigatorios:

- `status` (`pendente|consolidado|revisado|ativo|descartado`)

### Regra de consolidacao
Ao definir `status=consolidado`, os campos basicos do registro devem estar preenchidos:

- `estaca_inicial`
- `estaca_final`
- `tempo_manha`
- `tempo_tarde`
- `data`
- `frente_servico_id`
- `usuario_registrador_id`
- `resultado`

### Campos opcionais em registro

- `lado_pista` (preferencial)
- `pista` (alias legado)
- `observacao`
- `raw_text`

## Breaking/Compatibilidade

- Sem breaking para clientes que enviam `pista`; backend normaliza para `lado_pista`.
- Recomendacao para frontend novo: enviar apenas `lado_pista`.
- Endpoints `/api/v1/lancamentos/*` foram removidos e retornam `410 Gone`.

## Guia Rapido de Frontend

1. Listar mensagens recentes (`mensagens-campo`) para rastrear entrada.
2. Criar/editar registro (aceita payload parcial).
3. Completar campos obrigatorios de consolidacao.
4. Mudar status para `consolidado` em `registros/{id}/status`.
