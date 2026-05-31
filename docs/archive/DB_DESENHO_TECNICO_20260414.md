# Desenho Tecnico do Banco - Diario de Obra (2026-04-14)

## Objetivo

Formalizar o fluxo de dados de campo recebido via Telegram em duas camadas:

1. Ingestao bruta de mensagem
2. Registro oficial com status

Nota de dominio: o papel tecnico de campo permanece **encarregado**.

## Mudancas Estruturais Aplicadas

### 1) Integridade e simplificacao em `registros`

- Remocao da redundancia de coluna: `pista` (mantido alias de compatibilidade na aplicacao).
- `lado_pista` passa a ser a unica coluna persistida para lado da pista.
- Correcao de FK de `usuario_registrador_id` para `ON DELETE RESTRICT` (antes havia conflito com `NOT NULL`).
- Inclusao de:
  - `raw_text` (texto bruto associado ao registro consolidado)
  - `source_message_id` (vinculo com mensagem de origem)
  - `updated_at`
- Constraint de campos obrigatorios de registro nao exige mais `observacao`.

### 2) Nova camada de ingestao: `mensagens_campo`

Tabela para trilha completa de entrada de mensagens:

- Canal (`telegram`)
- IDs tecnicos do update/mensagem
- Usuario vinculado (quando houver)
- Texto bruto e texto normalizado
- Payload JSON bruto do update
- Hash de idempotencia
- Status de processamento (`pendente`, `processada`, `erro`)
- Erro de processamento

Uso principal:

- Rastreabilidade
- Evitar duplicidade por reentrega de update
- Diagnostico operacional

## Fluxo de Dados Atualizado

1. Mensagem chega no webhook/polling Telegram
2. Mensagem e persistida em `mensagens_campo` com hash de idempotencia
3. Usuario e resolvido por vinculo Telegram
4. Agente processa mensagem
5. Status da mensagem vira `processada` ou `erro`
6. Registro final pode vincular `registros.source_message_id`

## Compatibilidade Mantida

- API e tools continuam aceitando `pista` como entrada legada.
- Persistencia interna normaliza para `lado_pista`.
- Serializacao de registro continua retornando `pista` como alias para evitar quebra de clientes.

## Arquivos Principais Alterados

- `backend/db/models.py`
- `backend/db/repository.py`
- `backend/db/schema.sql`
- `backend/db/session.py`
- `backend/db/migrations/sql/20260414_011_registro_status_e_campos_opcionais.up.sql`
- `backend/db/migrations/sql/20260414_012_remocao_final_lancamentos.up.sql`
- `backend/services/telegram.py`
- `backend/api/routes/crud/registros.py`
- `backend/api/routes/crud/operacional.py`
- `backend/agents/tools/database_tools.py`

## Proxima Evolucao Recomendada

1. Registrar automaticamente `source_message_id` em `criar_registro` do agente/API.
2. Expandir consultas analiticas por `status` em `registros`.
