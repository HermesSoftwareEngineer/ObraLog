# Changelog - ObraLog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/).

---

## [2026-05-01] - Gateway do Agente com Tenant + Localizacao Dinamica

### 🔄 Alterado
- Runtime do agente (grafo) agora recebe contexto configuravel por tenant:
  - `tenant_id`
  - `obra_id_ativa`
  - `location_profile`
  - `location_labels`
  - `location_required_fields`
- `registrar_producao_diaria` no gateway passou a aceitar localizacao estruturada dinamica e manter alias legado (`estaca_inicial`, `estaca_final`).
- Checklist de `sugerir_campos_faltantes` ficou dinamico por perfil de localizacao (`estaca`, `km`, `texto`).
- System message do agente passou a incluir perfil de localizacao ativo para orientar perguntas e validacao.
- Tools internas de banco no agente foram reforcadas para operar com escopo de tenant em leituras e gravacoes.

### 🧪 Testes
- Novos cenarios de teste para:
  - perfil `km` e `texto` em `registrar_producao_diaria`
  - propagacao de tenant no gateway
  - checklist dinamico por perfil de localizacao no RAG

### 📚 Documentação Atualizada
- `docs/api-changes/20260501_gateway_tenant_localizacao.md`

---

## [2026-04-29] - Simplificação do Contrato da API de Alertas

### 🔄 Alterado
- `GET /api/v1/alertas` agora retorna payload de lista simplificado (focado em dados de card/tabela).
- Endpoints de retorno de alerta passam a usar payload de detalhe padronizado.
- Endpoints simples de tipos de alerta adicionados para consumo direto de frontend:
  - `GET /api/v1/alertas/tipos/simples`
  - `POST /api/v1/alertas/tipos/simples`
  - `PATCH /api/v1/alertas/tipos/simples/{tipo_id}`
  - `DELETE /api/v1/alertas/tipos/simples/{tipo_id}`
- Campos de usuário nos alertas agora incluem nome além do ID:
  - `reported_by_nome`
  - `read_by_nome`
  - `resolved_by_nome`
- `POST /api/v1/alertas/{alert_id}/read` agora inclui `leitura.worker_nome`.
- `POST /api/v1/alertas` agora exige `reported_at` em chamadas normais da API.
- Em chamadas com `source` de agente, `reported_at` é calculado automaticamente na data/hora de cadastro.
- Payloads de alerta passam a incluir o campo explícito `reported_at`.

### 🐛 Corrigido
- Fluxo de criação de alerta com `description` ausente agora resolve corretamente o `type` antes de montar descrição padrão.

### 📚 Documentação Atualizada
- `API_MAPEAMENTO.md`
- `docs/api-changes/STATUS_ENDPOINTS.md`
- `docs/api-changes/README.md`
- `docs/api-changes/20260429_alertas_payload_simplificado.md`

---

## [2026-04-14] - Fase 4 e 5: Remocao Definitiva e Hardening

### ✨ Adicionado
- Migration final de remocao: `backend/db/migrations/sql/20260414_012_remocao_final_lancamentos.up.sql`.

### ❌ Removido
- Classes ORM e repositórios de `Lancamento*`.
- Código morto de rotas `/api/v1/lancamentos/*`.
- Mappers e tools de gateway focados em lançamentos.
- Tipos/tabelas/índices de lançamento no schema base.

### 🔄 Alterado
- Runtime migration passa a dropar estruturas legadas de lançamento quando existirem.
- Documentação oficial atualizada para fluxo único de registros com status.

---

## [2026-04-14] - Redesenho Técnico do Banco para Diário de Obra

### 📝 Descrição Geral
Evolução do modelo de dados para suportar ingestão bruta de mensagens do Telegram, camada de lançamentos operacionais e correções de integridade em `registros`.

### ✨ Adicionado
- Novas tabelas:
  - `mensagens_campo`
  - `lancamentos_diario`
  - `lancamento_itens`
  - `lancamento_recursos`
  - `lancamento_midias`
- Novos campos em `registros`:
  - `raw_text`
  - `source_message_id`
  - `updated_at`
- Persistência de mensagens recebidas no fluxo Telegram com idempotência por hash.

### 🔄 Alterado
- `registros.usuario_registrador_id` agora usa `ON DELETE RESTRICT` para coerência com `NOT NULL`.
- Constraint `ck_registros_required_fields` ajustada para não exigir `observacao`.
- `pista` removido do schema físico; `lado_pista` permanece como campo único.
- API e tools mantêm compatibilidade de entrada para `pista` (alias legado), normalizando para `lado_pista`.

### 📋 Arquivos Modificados
- `backend/db/models.py`
- `backend/db/repository.py`
- `backend/db/schema.sql`
- `backend/db/session.py`
- `backend/services/telegram.py`
- `backend/api/routes/crud.py`
- `backend/agents/tools/database_tools.py`
- `SETUP_DB.md`
- `docs/README.md`

### 🔢 Database
- Migration UP: `backend/db/migrations/sql/20260414_010_ingestao_lancamentos_e_integridade_registros.up.sql`
- Migration DOWN: `backend/db/migrations/sql/20260414_010_ingestao_lancamentos_e_integridade_registros.down.sql`
- Documento técnico: `docs/DB_DESENHO_TECNICO_20260414.md`

---

## [2026-04-14] - Atualização de API para Frontend

### ✨ Adicionado
- Endpoints para rastreabilidade operacional:
  - `GET /api/v1/mensagens-campo`
  - `GET /api/v1/mensagens-campo/{mensagem_id}`
- Endpoints para ciclo completo de lançamentos:
  - `GET/POST /api/v1/lancamentos`
  - `PATCH /api/v1/lancamentos/{lancamento_id}`
  - `POST /api/v1/lancamentos/{lancamento_id}/itens`
  - `POST /api/v1/lancamentos/{lancamento_id}/recursos`
  - `POST /api/v1/lancamentos/{lancamento_id}/midias`
  - `POST /api/v1/lancamentos/{lancamento_id}/confirmar`
  - `POST /api/v1/lancamentos/{lancamento_id}/descartar`
  - `POST /api/v1/lancamentos/{lancamento_id}/consolidar`

### 🔄 Alterado
- Contrato de registros atualizado para frontend:
  - `lado_pista` é campo técnico preferencial
  - `pista` mantido como alias legado compatível

### 📚 Documentação Atualizada
- `API_MAPEAMENTO.md`
- `docs/api-changes/STATUS_ENDPOINTS.md`
- `docs/api-changes/README.md`
- `docs/api-changes/20260414_api_frontend_lancamentos_mensagens.md`

---

## [2026-04-05] - Alterações nos Modelos de Frente de Serviço e Registros

### 📝 Descrição Geral
Ajuste dos campos obrigatórios e opcionais, adição de campo de observação e remoção do campo `hora_registro` (redundante com `created_at`).

### ✨ Adicionado
- **Frentes de Serviço**: Campo `observacao` (texto, opcional)
- **Registros**: Campo `observacao` (texto, opcional)

### 🔄 Alterado
- **Frentes de Serviço**: 
  - `encarregado_responsavel` agora é opcional (antes era optional, mas agora mais claro)
  - Apenas `nome` é obrigatório

- **Registros**:
  - `frente_servico_id` agora é **obrigatório** (antes era opcional)
  - `data` agora é **opcional** (antes era obrigatório)
  - `usuario_registrador_id` agora é **opcional** (antes era obrigatório)
  - Demais campos (`estaca_inicial`, `estaca_final`, `resultado`, `tempo_manha`, `tempo_tarde`, `pista`, `lado_pista`) permanecem opcionais

### ❌ Removido
- **Registros**: Campo `hora_registro` removido. Use `created_at` para obter o timestamp de criação do registro.

### 📋 Arquivos Modificados
- `backend/db/models.py` - Modelos SQLAlchemy
- `backend/db/schema.sql` - Schema do banco de dados
- `backend/db/repository.py` - Métodos de persistência
- `backend/api/routes/crud.py` - Endpoints REST
- `backend/agents/tools/database_tools.py` - Tools dos agentes

### 🔢 Database
- Migration UP: `backend/db/migrations/sql/20260405_004_update_frente_servico_registros.up.sql`
- Migration DOWN: `backend/db/migrations/sql/20260405_004_update_frente_servico_registros.down.sql`

---
