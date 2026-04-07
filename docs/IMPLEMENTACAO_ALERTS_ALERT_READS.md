# Implementacao de Alerts e Alert Reads

## Objetivo
Documentar integralmente a solicitacao para criacao das tabelas `alerts` e `alert_reads`, incluindo escopo, gaps tecnicos no projeto atual ObraLog, plano de execucao e checklist de entrega.

## Solicitacao recebida (resumo)
Criar modelos e migracoes para:
- `alerts`
- `alert_reads`

Com stack esperado no pedido:
- FastAPI + SQLAlchemy async
- Alembic em `backend/alembic/versions/`
- Tabelas base existentes: `workers` e `obras`

Tambem foi solicitado:
1. Modelos SQLAlchemy 2.0 com `mapped_column` e `type hints`
2. Geracao e ajuste de migracao Alembic
3. `alembic upgrade head`
4. Validacao no banco com comandos SQL
5. Criacao de `backend/db/alert_repository.py` com assinaturas async

## Diagnostico do projeto ObraLog atual
O estado atual do repositorio nao bate com o stack assumido no prompt.

Evidencias no codigo:
- Modelos atuais usam estilo classico com `Column(...)`, nao `mapped_column`:
  - `backend/db/models.py`
- Sessao atual e sincronica (`create_engine`, `sessionmaker`), sem async engine/session:
  - `backend/db/session.py`
- Estrutura de migracao atual e por SQL manual em:
  - `backend/db/migrations/sql/`
- Nao existe estrutura Alembic no repositorio:
  - ausencia de `backend/alembic/versions/`
  - ausencia de `alembic.ini`
- Nao existem tabelas/modelos `workers` e `obras` neste projeto.

## Impacto pratico
A execucao literal do prompt nao e segura neste repositorio sem uma etapa previa de adaptacao arquitetural, porque:
- Gerar migracao Alembic nao e possivel sem configurar Alembic.
- FKs para `workers(id)` e `obras(id)` falhariam porque essas tabelas nao existem no schema atual.
- Forcar SQLAlchemy async em arquivo atual quebraria padrao do projeto.

## Plano recomendado para implementar aqui (adaptado ao ObraLog)

### Fase A - Decisao de nomenclatura e referencia
1. Definir se as FKs devem apontar para tabelas existentes do ObraLog:
   - `workers` -> `usuarios`
   - `obras` -> `frentes_servico` (ou criar `obras` formalmente)
2. Definir se IDs serao UUID apenas nas novas tabelas ou padronizar projeto todo.

### Fase B - Modelos no padrao atual do repositorio
1. Adicionar `Alert` e `AlertRead` em `backend/db/models.py` mantendo o estilo atual (`Column`).
2. Declarar enums de dominio (`type`, `severity`, `status`).
3. Declarar arrays PostgreSQL para `photo_urls` e `notified_channels`.
4. Criar relacionamentos navegaveis.

### Fase C - Migracoes no padrao atual do repositorio
1. Criar dois scripts SQL em `backend/db/migrations/sql/`:
   - `*.up.sql` com `CREATE TABLE alerts` e `CREATE TABLE alert_reads`
   - `*.down.sql` com `DROP TABLE` na ordem correta (`alert_reads` antes de `alerts`)
2. Garantir:
   - `UNIQUE (alert_id, worker_id)` em `alert_reads`
   - `ON DELETE CASCADE` em `alert_reads.alert_id`
   - tipos e defaults conforme especificacao

### Fase D - Runtime migration / init
1. Atualizar `backend/db/init_db.py` e/ou `backend/db/session.py` para garantir criacao/alteracoes sem quebrar ambientes ja em execucao.
2. Rodar validacoes SQL no PostgreSQL para confirmar schema final.

### Fase E - Repositorio async (somente assinatura)
1. Criar `backend/db/alert_repository.py` com assinaturas async e docstrings, sem implementacao.
2. Referenciar tipos `Alert` e `AlertRead`.

## Contrato de assinaturas solicitado
```python
async def create_alert(...) -> Alert
async def get_alert_by_id(alert_id: UUID) -> Alert | None
async def get_alert_by_code(code: str) -> Alert | None
async def list_alerts_by_obra(obra_id: UUID, status: str | None) -> list[Alert]
async def update_alert_status(alert_id: UUID, status: str, resolved_by: UUID | None) -> Alert
async def mark_as_read(alert_id: UUID, worker_id: UUID) -> AlertRead
async def list_unread_by_worker(worker_id: UUID, obra_id: UUID) -> list[Alert]
async def generate_alert_code(obra_id: UUID) -> str  # ex: ALT-2024-0042
```

## Checklist de entrega (status nesta rodada)
- [x] Modelos adicionados em `backend/db/models.py`
- [x] Migracao criada no padrao atual do projeto (`backend/db/migrations/sql/20260407_008_create_alerts_and_alert_reads.*`)
- [ ] Migracao aplicada no banco e validada com comandos SQL
- [x] `backend/db/alert_repository.py` criado com assinaturas

## Motivo do status pendente
As pendencias restantes dependem de execucao em banco (aplicar scripts e inspecionar estrutura com comandos SQL). A parte de codigo ja foi implementada no padrao do ObraLog.

## Proximo passo objetivo
Se a decisao for seguir no stack atual do ObraLog, executar a implementacao adaptada (Fases A-E) usando:
- modelos SQLAlchemy sincronicos no estilo existente
- migracoes SQL em `backend/db/migrations/sql/`
- repositario com assinaturas async conforme solicitado
