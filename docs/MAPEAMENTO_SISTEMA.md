# ObraLog — Relatório Técnico do Sistema

Gerado em: 2026-05-24  
Base: leitura direta dos arquivos-fonte em `ObraLog/` e `ObraLogFront/`

---

## 1. Visão geral e objetivos do sistema

ObraLog é um SaaS B2B multi-tenant para gestão de diários de obra em construção civil. O produto permite que **encarregados de campo** registrem produção diária via **Telegram** (e opcionalmente WhatsApp), e que **gerentes e administradores** aprovem, consolidem e exportem relatórios via **dashboard web**.

O diferencial central é o **agente de IA** (LangGraph + Gemini 2.5 Flash) que conduz a conversa no Telegram: coleta dados de forma parcial e iterativa, valida campos obrigatórios e aprova registros autonomamente quando todos os requisitos são satisfeitos.

**Stack resumida:**

| Camada | Tecnologias |
|--------|-------------|
| Backend | Python 3.10+, Flask 3.1.3, SQLAlchemy 2.0.49 |
| Banco de dados | PostgreSQL (Supabase), pgvector 0.3.0+ |
| IA / Agente | LangGraph 1.1.6, Gemini 2.5 Flash (`langchain-google-genai 4.2.1`) |
| Embeddings | Google `text-multilingual-embedding-002` → **768 dims** |
| Messaging | python-telegram-bot 22.7, Meta WhatsApp Cloud API |
| Storage | Supabase Storage (PDFs de diários) |
| Auth | JWT via itsdangerous `URLSafeTimedSerializer` |
| Geração de docs | ReportLab 4.0+, openpyxl 3.1+, python-docx 1.1+ |
| Frontend | React 19.2, Vite 8, Tailwind CSS 4.2, React Router 7.14 |

---

## 2. Estrutura de diretórios e módulos

```
ObraLog-united/
├── ObraLog/                        # Repositório backend
│   ├── backend/
│   │   ├── main.py                 # Entry point Flask — registra blueprints, inicia bot
│   │   ├── core/
│   │   │   ├── config.py           # Pydantic Settings (carrega .env)
│   │   │   └── logger.py           # Logger centralizado
│   │   ├── db/
│   │   │   ├── models.py           # Todos os modelos SQLAlchemy (enums + 18 entidades)
│   │   │   ├── session.py          # Engine, SessionLocal, ensure_runtime_migrations()
│   │   │   ├── repository.py       # Repository pattern (CRUD genérico)
│   │   │   ├── alert_repository.py # Queries especializadas de alertas
│   │   │   ├── diario_repository.py# Queries especializadas de diários
│   │   │   └── init_db.py          # Script de inicialização (uso manual)
│   │   ├── api/
│   │   │   ├── schemas.py          # Pydantic schemas para validação de entrada
│   │   │   ├── schemas_diario.py   # Schemas específicos de diários (dataclasses out)
│   │   │   └── routes/
│   │   │       ├── auth.py         # Blueprint auth_v1 → /api/v1/auth/*
│   │   │       ├── diario.py       # Blueprints diario_v1, diarios_v1, diarios_files_v1
│   │   │       ├── alerts.py       # Blueprint alerts_v1 → /api/v1/alertas/*
│   │   │       ├── chat.py         # Blueprint chat_v1 → /api/v1/chat/*
│   │   │       ├── dashboard.py    # Blueprint dashboard_v1 → /api/v1/dashboard/*
│   │   │       ├── tenant.py       # Blueprint tenant_v1 → /api/v1/tenant/*
│   │   │       ├── admin.py        # Blueprint admin_v1 → /api/v1/admin/*
│   │   │       ├── reports.py      # Blueprint reports → /api/v1/reports/*
│   │   │       ├── webhook.py      # Blueprint telegram → POST /telegram/webhook
│   │   │       ├── whatsapp_webhook.py # Blueprint whatsapp → POST/GET /whatsapp/webhook
│   │   │       └── crud/
│   │   │           ├── base.py             # api_blueprint → /api/v1
│   │   │           ├── registros.py        # CRUD Registros
│   │   │           ├── obras.py            # CRUD Obras
│   │   │           ├── frentes_servico.py  # CRUD Frentes de Serviço
│   │   │           ├── usuarios.py         # CRUD Usuários
│   │   │           ├── tipos_obra.py       # CRUD Tipos de Obra
│   │   │           ├── registro_schemas.py # CRUD Schemas de Registro
│   │   │           ├── operacional.py      # Endpoints operacionais auxiliares
│   │   │           └── agent_instructions.py # GET/POST instruções do agente
│   │   ├── agents/
│   │   │   ├── graph.py            # StateGraph LangGraph (START→agent→tools→END)
│   │   │   ├── state.py            # State TypedDict com messages Annotated[add_messages]
│   │   │   ├── llms.py             # ChatGoogleGenerativeAI + embeddings com fallback
│   │   │   ├── prompts.py          # SYSTEM_PROMPT_BASE + build_system_prompt()
│   │   │   ├── chat.py             # Função de entrada para conversa via API web
│   │   │   ├── chat_db.py          # PostgresSaver (LangGraph checkpointer)
│   │   │   ├── session_service.py  # get_or_create_conversa, buscar_memorias_relevantes
│   │   │   ├── instructions_store.py # Leitura de instruções editáveis em arquivo
│   │   │   ├── telegram_bot.py     # Helpers específicos Telegram para o bot
│   │   │   ├── nodes/
│   │   │   │   ├── response.py     # agent_step, tools_step, should_continue_to_tools
│   │   │   │   ├── intent.py       # Detecção de intenção (helper)
│   │   │   │   ├── machine.py      # Módulo auxiliar (contextos de máquinas)
│   │   │   │   └── productivity.py # Módulo auxiliar (análise de produtividade)
│   │   │   ├── gateway/
│   │   │   │   ├── contracts.py    # ActorContext, GatewayRequest, GatewayResponse, WriteOptions
│   │   │   │   ├── policies.py     # GatewayPolicyService (assert_can_read/write/intent)
│   │   │   │   ├── gateway_service.py # GatewayService (execute_consulta, execute_execucao)
│   │   │   │   ├── mappers.py      # map_registro_to_business, strip_technical_keys
│   │   │   │   ├── location_profile.py # build_location_profile, resolve_runtime_location_context
│   │   │   │   ├── rag_service.py  # BusinessRAGService (sugerir_campos_faltantes)
│   │   │   │   ├── errors.py       # GatewayError, GatewayPermissionDenied, GatewayValidationError
│   │   │   │   └── routes.py       # Blueprint do gateway (uso interno/testes)
│   │   │   ├── context/
│   │   │   │   └── vector_context.py # get_context_for_query (RAG via pgvector)
│   │   │   └── tools/
│   │   │       ├── gateway_tools.py  # Todas as tools expostas ao LLM (closure por contexto)
│   │   │       ├── database_tools.py # Factory get_database_tools (tools diretas sem gateway)
│   │   │       ├── telegram_tools.py # Tools específicas do Telegram (enviar msg, poll, etc.)
│   │   │       └── database/
│   │   │           ├── registros.py      # Tool implementations de registros
│   │   │           ├── obras.py          # Tool implementations de obras
│   │   │           ├── frentes_servico.py# Tool implementations de frentes
│   │   │           ├── usuarios.py       # Tool implementations de usuários
│   │   │           ├── alerts.py         # Tool implementations de alertas
│   │   │           ├── alert_types.py    # Tool implementations de tipos de alerta
│   │   │           ├── mensagens_campo.py# Tool implementations de mensagens
│   │   │           └── common.py         # Utilitários comuns entre tools
│   │   ├── services/
│   │   │   ├── telegram.py             # Entry points: start_polling, set_webhook, handle_update
│   │   │   ├── telegram_processor.py   # MessageProcessor: extrai → persiste → invoca agente → responde
│   │   │   ├── telegram_poller.py      # Loop de polling (dev mode)
│   │   │   ├── telegram_client.py      # BotClient: HTTP wrapper para Telegram API
│   │   │   ├── telegram_extractor.py   # MessageExtractor: parse de update JSON
│   │   │   ├── telegram_linker.py      # UserLinker: vincula chat_id ao usuário
│   │   │   ├── telegram_persistence.py # Persistência de estado de sessão
│   │   │   ├── telegram_poll.py        # PollAnswerHandler (enquetes)
│   │   │   ├── telegram_typing.py      # TypingIndicator (sendChatAction)
│   │   │   ├── whatsapp.py             # Entry points WhatsApp
│   │   │   ├── whatsapp_client.py      # HTTP client para Meta API
│   │   │   ├── whatsapp_processor.py   # Análogo ao telegram_processor
│   │   │   ├── whatsapp_extractor.py   # Parse de payload WhatsApp
│   │   │   ├── whatsapp_linker.py      # Vinculação de número ao usuário
│   │   │   ├── whatsapp_persistence.py # Persistência WhatsApp
│   │   │   ├── diario_service.py       # Geração de diários: gerar_ou_regerar_diario
│   │   │   ├── pdf_service.py          # Geração de PDF (ReportLab)
│   │   │   ├── excel_service.py        # Exportação Excel (openpyxl)
│   │   │   ├── word_service.py         # Exportação Word (python-docx)
│   │   │   └── notifications.py        # Placeholder (não implementado)
│   │   ├── jobs/
│   │   │   ├── gerar_diarios_diarios.py # Cron: gera diários do dia para obras ativas
│   │   │   └── encerrar_conversas.py    # Cron: encerra conversas por timeout
│   │   └── utils/
│   │       ├── embeddings.py           # (referenciado em llms.py)
│   │       └── storage.py              # Upload para Supabase Storage
│   └── .env                            # Variáveis de ambiente (dev)
│
└── ObraLogFront/                       # Repositório frontend
    └── src/
        ├── App.jsx                     # React Router — todas as rotas
        ├── contexts/
        │   ├── AuthContext.jsx         # Estado de autenticação global
        │   └── ThemeContext.jsx        # Dark/light theme
        ├── components/
        │   ├── DashboardShell.jsx      # Layout principal (sidebar + conteúdo + rail)
        │   ├── DashboardSidebar.jsx    # Navegação lateral
        │   ├── AlertasRightRail.jsx    # Painel de alertas (coluna direita)
        │   ├── ProtectedRoute.jsx      # Wrapper de rotas autenticadas + RBAC
        │   └── alerts/                 # Componentes de alerta
        ├── pages/                      # 17 páginas (ver seção 4)
        └── services/                   # 16 arquivos de serviço/cliente de API
```

---

## 3. Modelos de dados

Todos os modelos vivem em `backend/db/models.py`. O esquema é criado/mantido por `ensure_runtime_migrations()` em `session.py` (DDL imperativo, idempotente, executado a cada start).

### Enums Python (todos com `values_callable=_enum_values` → armazena `.value`)

| Enum | Valores |
|------|---------|
| `NivelAcesso` | `administrador`, `gerente`, `encarregado` |
| `Clima` | `limpo`, `nublado`, `impraticavel` |
| `LadoPista` | `direito`, `esquerdo` |
| `AlertType` | `maquina_quebrada`, `acidente`, `falta_material`, `risco_seguranca`, `outro` |
| `AlertSeverity` | `baixa`, `media`, `alta`, `critica` |
| `AlertStatus` | `aberto`, `em_atendimento`, `aguardando_peca`, `resolvido`, `cancelado` |
| `RegistroStatus` | `pendente`, `aprovado`, `rejeitado` |
| `DiarioTipo` | `diario`, `semanal`, `mensal` |
| `DiarioStatus` | `rascunho`, `finalizado` |
| `CanalOrigemMensagem` | `telegram`, `whatsapp` |
| `ConteudoMensagemTipo` | `texto`, `foto`, `audio`, `misto` |
| `ProcessamentoMensagemStatus` | `pendente`, `processada`, `erro` |
| `DirecaoMensagem` | `user`, `agent` |

### Entidades

#### `Tenant` (tabela: `tenants`)
Raiz do multi-tenancy. Todo dado tem `tenant_id`.
- PK: `id` (Integer)
- `nome`, `slug` (unique), `tipo_negocio`, `ativo`
- `location_type` (String 50, default `"estaca"`) — perfil de localização da obra
- `timeout_conversa_minutos` (Integer, default 60) — para job de encerramento de conversas
- Dados comerciais: `cnpj`, `razao_social`, `nome_fantasia`, endereço completo, `telefone_comercial`, `email_comercial`
- Relacionamentos: `usuarios`, `obras`, `frentes_servico`, `registros`, `mensagens_campo`, `alerts`, `alert_type_aliases`, `telegram_link_codes`, `user_invite_codes`, `registro_schemas`, `usuario_obras`, `conversas`, `diarios`, `tipos_obra`

#### `TipoObra` (tabela: `tipos_obra`)
Categorização de obras (ex: rodovia, ferrovia). Unique constraint em `(tenant_id, slug)`.
- PK: `id`, FK: `tenant_id`
- `slug`, `nome`, `descricao`, `ativo`
- Relacionamentos: `obras`, `registro_schemas`

#### `Obra` (tabela: `obras`)
Projeto de construção. Unique constraint em `(tenant_id, codigo)`.
- PK: `id`, FKs: `tenant_id`, `tipo_obra_id` (SET NULL)
- `nome`, `codigo`, `descricao`, `ativo`, `tipo_obra` (texto legado), `tipo_obra_id` (FK)
- Relacionamentos: `registros`, `alerts`, `frentes_servico`, `usuario_obras`, `diarios`

#### `Usuario` (tabela: `usuarios`)
Usuário do sistema. Unique constraint em `(tenant_id, email)`.
- PK: `id`, FK: `tenant_id`
- `nome`, `email`, `senha` (hash pbkdf2/scrypt ou plaintext em dev)
- `telefone` (unique, nullable), `telegram_chat_id` (unique, nullable), `telegram_thread_id` (unique, nullable)
- `nivel_acesso`: enum `NivelAcesso`
- Relacionamentos: `frentes_servico`, `registros`, `telegram_link_codes`, `alerts_reportados`, `alerts_resolvidos`, `alerts_lidos`, `alert_reads`, `mensagens_campo`, `usuario_obras`, `conversas`

#### `FrenteServico` (tabela: `frentes_servico`)
Equipe ou seção de trabalho vinculada a uma obra e a um schema de campos.
- PK: `id`, FKs: `tenant_id`, `obra_id` (SET NULL), `encarregado_responsavel` (SET NULL), `registro_schema_id` (SET NULL)
- `nome`, `observacao`

#### `RegistroSchema` (tabela: `registro_schemas`)
Define quais campos são obrigatórios/opcionais para uma frente de serviço.
- PK: `id`, FKs: `tenant_id`, `tipo_obra_id` (RESTRICT)
- `nome`, `tipo_obra` (texto legado)
- `campos_ativos` (JSON): definições de campos obrigatórios
- `campos_extras` (JSON): array de campos customizados com labels
- `ativo`

#### `Registro` (tabela: `registros`)
Entrada diária de produção. O modelo central do sistema.
- PK: `id`, FKs: `tenant_id`, `obra_id` (SET NULL), `frente_servico_id` (CASCADE), `usuario_registrador_id` (RESTRICT), `registro_schema_id` (SET NULL), `source_message_id` (SET NULL → UUID ref `mensagens_campo`)
- `status`: enum `RegistroStatus` (default `pendente`)
- `data` (Date, nullable), `resultado` (DECIMAL 10,2, nullable)
- **Localização**: `estaca_inicial`, `estaca_final` (DECIMAL 10,2), `localizacao` (String), `metadata_json` (JSON)
- **Clima**: `tempo_manha`, `tempo_tarde` (enum `Clima`)
- `lado_pista`: enum `LadoPista`
- `observacao` (String), `raw_text` (Text — texto original do Telegram)
- `created_at`, `updated_at`
- Property `pista` / setter → alias para `lado_pista`
- Relacionamentos: `imagens` (cascade), `frente_servico`, `obra`, `usuario_registrador`, `source_message`

#### `RegistroImagem` (tabela: `registro_imagens`)
Imagem vinculada a um registro.
- PK: `id`, FKs: `registro_id` (CASCADE), `tenant_id`
- `storage_path` (local), `external_url` (Supabase), `mime_type`, `file_size`, `origem` (default `"api"`)

#### `UsuarioObra` (tabela: `usuario_obras`)
Relação M:N entre usuário e obra. Unique em `(usuario_id, obra_id)`.
- `ativo`, `eh_padrao` (boolean — marca obra padrão do usuário)

#### `MensagemCampo` (tabela: `mensagens_campo`)
Histórico de mensagens recebidas/enviadas pelo bot.
- PK: `id` (UUID, `gen_random_uuid()`)
- `canal`: enum `CanalOrigemMensagem`
- `telegram_chat_id`, `telegram_message_id` (BigInt), `telegram_update_id` (BigInt)
- `usuario_id` (SET NULL)
- `tipo_conteudo`: enum `ConteudoMensagemTipo`
- `texto_bruto`, `texto_normalizado`, `payload_json` (Text)
- `hash_idempotencia` (VARCHAR 120, unique) — previne reprocessamento
- `status_processamento`: enum `ProcessamentoMensagemStatus`
- `erro_processamento`, `direcao`: enum `DirecaoMensagem`
- Índice único: `(canal, telegram_chat_id, telegram_message_id)` WHERE message_id NOT NULL

#### `TelegramLinkCode` (tabela: `telegram_link_codes`)
Código para vincular chat_id a um usuário.
- PK: `id`, FKs: `user_id` (CASCADE), `tenant_id`, `generated_by_user_id` (SET NULL)
- `code` (VARCHAR 32, unique), `expires_at`, `used_at`

#### `UserInviteCode` (tabela: `user_invite_codes`)
Convite para cadastro de novo usuário.
- PK: `id` (UUID), FKs: `tenant_id` (CASCADE), `criado_por` (RESTRICT), `usado_por` (SET NULL)
- `email_destinatario`, `codigo` (unique), `nivel_acesso`, `expira_em`, `usado_em`, `ativo`

#### `Alert` (tabela: `alerts`)
Incidente operacional reportado. Unique em `(tenant_id, code)`.
- PK: `id` (UUID), FKs: `tenant_id` (RESTRICT), `reported_by`, `obra_id` (SET NULL), `resolved_by`, `read_by`
- `code` (ex: ALT-001), `type` (String 120), `severity`: enum `AlertSeverity`
- `title`, `description`, `raw_text`, `location_detail`, `equipment_name`
- `photo_urls` (ARRAY String), `status`: enum `AlertStatus`
- `priority_score` (SmallInt), `notified_at`, `notified_channels` (ARRAY String)
- `resolved_at`, `resolution_notes`, `is_read`, `read_at`
- Relacionamentos: `reads` (AlertRead, cascade)

#### `AlertRead` (tabela: `alert_reads`)
Rastreia leitura individual de alerta por worker. Unique em `(alert_id, worker_id)`.

#### `AlertTypeAlias` (tabela: `alert_type_aliases`)
Normalização de tipos de alerta customizados por tenant. Unique em `(tenant_id, alias)` e `(tenant_id, normalized_alias)`.
- `alias`, `normalized_alias`, `canonical_type`, `descricao`, `ativo`, `created_by`, `updated_by`

#### `Conversa` (tabela: `conversas`)
Sessão de diálogo do bot com um usuário.
- PK: `id` (BigSerial), FKs: `tenant_id` (CASCADE), `usuario_id` (CASCADE)
- `chat_id`, `thread_id`, `iniciada_em`, `encerrada_em`, `ultima_msg_em`
- `resumo` (Text), `embedding` (Vector 768 — pgvector; fallback Text se pgvector indisponível)
- `ambiente` (String 10, default `'prod'`) — para filtrar conversas dev vs. prod

#### `Diario` (tabela: `diarios`)
Compilação de registros em documento. Unique constraint: `(obra_id, tipo, data_inicio, data_fim)`.
- PK: `id` (UUID), FKs: `obra_id` (RESTRICT), `tenant_id` (RESTRICT), `gerado_por` (SET NULL), `finalizado_por` (SET NULL)
- `tipo`: enum `DiarioTipo`, `status`: enum `DiarioStatus`
- `data_inicio`, `data_fim` (Date), `versao_atual` (Integer)
- Relacionamentos: `versoes` (DiarioVersao, cascade, order by versao), `registros_vinculados` (DiarioRegistro, cascade)

#### `DiarioRegistro` (tabela: `diario_registros`)
Junção entre diário e registro. Unique em `(diario_id, registro_id)`.
- `diario_id` (UUID, CASCADE), `registro_id` (RESTRICT)

#### `DiarioVersao` (tabela: `diario_versoes`)
Versão histórica de um PDF de diário. Unique em `(diario_id, versao)`.
- PK: `id` (UUID), FKs: `diario_id` (CASCADE), `tenant_id` (RESTRICT), `gerado_por` (SET NULL)
- `versao` (Int), `storage_path` (String), `storage_url` (String — Supabase signed URL)
- `motivo_regeracao` (Text), `registros_ids` (JSON), `include_pending` (Boolean)

---

## 4. Rotas REST

### Autenticação — `auth_blueprint` (`/api/v1/auth`)
Arquivo: `backend/api/routes/auth.py`

| Método | Rota | Auth | Nível | Descrição |
|--------|------|------|-------|-----------|
| POST | `/register` | Não | — | Cadastro com invite_code; retorna token JWT |
| POST | `/login` | Não | — | Login email/senha; retorna token JWT |
| GET | `/me` | Sim | Qualquer | Dados do usuário autenticado |
| PATCH | `/link-telegram` | Sim | Qualquer | Vincula telegram_chat_id ao usuário |
| POST | `/telegram-link-codes` | Sim | Admin | Gera código de vínculo Telegram para usuário |
| POST | `/invite-codes` | Sim | Admin/Gerente | Cria código de convite (expira 24h) |
| GET | `/invite-codes` | Sim | Admin/Gerente | Lista convites ativos do tenant |
| DELETE | `/invite-codes/{codigo}` | Sim | Admin/Gerente | Cancela convite |

**Middleware `require_auth`**: extrai `Bearer <token>`, decodifica com `URLSafeTimedSerializer`, popula `g.current_user` e `g.tenant_id`. Token expira em `AUTH_TOKEN_MAX_AGE_SECONDS` (default 86400s = 24h).

---

### CRUD Operacional — `api_blueprint` (`/api/v1`)
Arquivo: `backend/api/routes/crud/`

**Registros** (`/api/v1/registros`):

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/registros` | Lista com filtros (obra_id, data, frente, status) + paginação (page, per_page) |
| POST | `/registros` | Cria registro (status inicial = pendente) |
| GET | `/registros/{id}` | Detalhe com imagens |
| PATCH | `/registros/{id}` | Atualização parcial (inclui mudança de status) |
| POST | `/registros/{id}/imagens` | Upload de imagem (MIME validado, salvo em `uploads/registros/`) |
| DELETE | `/registros/{id}/imagens/{img_id}` | Remove imagem |

**Obras** (`/api/v1/obras`), **Frentes** (`/api/v1/frentes-servico`), **Usuários** (`/api/v1/usuarios`), **Tipos de Obra** (`/api/v1/tipos-obra`), **Schemas** (`/api/v1/registro-schemas`): CRUD padrão.

**Instruções do Agente** (`/api/v1/agent-instructions`): GET/POST para editar o prompt customizável.

---

### Diários — `diario_v1`, `diarios_v1`, `diarios_files_v1`
Arquivo: `backend/api/routes/diario.py`

**Blueprint `diario_v1`** (`/api/v1/diario`) — endpoints legados:
- `GET /diario/do-dia` — diário do dia para uma obra
- `GET /diario/relatorio` — relatório por período

**Blueprint `diarios_v1`** (`/api/v1/diarios`) — endpoints novos CRUD:

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/diarios/gerar` | Gera ou regera diário; body: obra_id, tipo, data_inicio, data_fim; query: include_pending |
| GET | `/diarios` | Lista diários filtrados (obra_id, tipo, data range) com paginação |
| GET | `/diarios/{id}` | Detalhe do diário com versões |
| GET | `/diarios/{id}/versoes` | Histórico de versões/PDFs |
| PATCH | `/diarios/{id}/finalizar` | Muda status para FINALIZADO |

**Blueprint `diarios_files_v1`** (`/api/v1/diarios-files`) — download de exports:
- `GET /diarios-files/{id}/excel` — exporta Excel
- `GET /diarios-files/{id}/word` — exporta Word

---

### Alertas — `alerts_router` (`/api/v1/alertas`)
Arquivo: `backend/api/routes/alerts.py`

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/alertas` | Cria alerta (gera code ALT-NNN, normaliza tipo via AlertTypeAlias) |
| GET | `/alertas` | Lista com filtros (status, severity, obra_id, nao_lidos) + paginação |
| GET | `/alertas/{id}` | Detalhe completo |
| PATCH | `/alertas/{id}` | Atualiza status, resolução, resolution_notes |
| PATCH | `/alertas/{id}/marcar-lido` | Registra leitura em AlertRead |
| GET | `/alertas/tipos` | Lista tipos/aliases |
| GET | `/alertas/tipos/{id}` | Detalhe de tipo/alias |

---

### Chat — `chat_router` (`/api/v1/chat`)
Arquivo: `backend/api/routes/chat.py`

| Método | Rota | Nível | Descrição |
|--------|------|-------|-----------|
| GET | `/chat/conversas` | Admin | Lista conversas com paginação e filtro por ambiente |
| GET | `/chat/conversas/{chat_id}` | Admin | Histórico de mensagens de uma conversa |

---

### Dashboard — `dashboard_blueprint` (`/api/v1/dashboard`)
Arquivo: `backend/api/routes/dashboard.py`
- KPIs: registros por período/status/frente, alertas por severity, diários gerados

### Tenant — `tenant_blueprint` (`/api/v1/tenant`)
- GET `/tenant` — dados completos do tenant autenticado

### Admin — `admin_blueprint` (`/api/v1/admin`)
- POST `/admin/switch-tenant` — alterna tenant (super-admin)

### Webhooks
- `POST /telegram/webhook` — recebe updates do Telegram (Telegram Blueprint)
- `GET /whatsapp/webhook` — verificação de webhook Meta
- `POST /whatsapp/webhook` — recebe mensagens WhatsApp

### Outros
- `GET /health` → `{"status": "ok"}`
- `GET /` → `{"message": "..."}`
- `GET /backend/uploads/registros/<filename>` — serve imagens de registros (path-traversal protegido)

---

### Rotas Frontend (React Router — `App.jsx`)

| Rota | Componente | Nível mínimo |
|------|-----------|--------------|
| `/` | LandingPage | Público |
| `/login` | LoginPage | Público (redireciona se autenticado) |
| `/cadastro` | CadastroPage | Público |
| `/dashboard` | DashboardPage | Qualquer autenticado |
| `/dashboard/usuarios` | UsuariosPage | Admin/Gerente |
| `/dashboard/frentes-servico` | FrentesServicoPage | Qualquer |
| `/dashboard/conversas` | MensagensCampoPage | Admin |
| `/dashboard/registros` | RegistrosPage | Qualquer |
| `/dashboard/diario-obra` | DiarioObraPage | Qualquer |
| `/dashboard/diario-obra/:id/visualizar` | DiarioObraVisualizacaoPage | Qualquer |
| `/dashboard/obras` | ObrasPage | Qualquer |
| `/dashboard/agent/instrucoes` | AgentInstructionsPage | Admin |
| `/dashboard/configuracoes` | ConfiguracoesPage | Admin/Gerente |
| `/dashboard/configuracoes/tabelas-auxiliares` | TabelasAuxiliaresPage | Admin/Gerente |
| `/dashboard/configuracoes/unidade` | GerenciarUnidadePage | Admin/Gerente |
| `/dashboard/configuracoes/unidades` | GerenciarUnidadesPage | Admin |
| `/dashboard/configuracoes/tabelas-auxiliares/schemas` | RegistroSchemasPage | Admin/Gerente |
| `/dashboard/configuracoes/tabelas-auxiliares/tipos-alerta` | TiposAlertaPage | Admin/Gerente |
| `/dashboard/configuracoes/tabelas-auxiliares/tipos-obra` | TiposObraPage | Admin/Gerente |
| `/dashboard/mensagens-campo` | → redirect `/dashboard/conversas` | — |
| `/dashboard/diario-obra/visualizar` | → redirect `/dashboard/diario-obra` | — |

---

## 5. Serviços e lógica de negócio

### `telegram.py` — Orquestrador do bot
- Instancia `MessageProcessor` e `PollAnswerHandler` na importação
- `_ImageBatchDebouncer`: agrupa fotos de um mesmo chat enviadas em rápida sucessão (aguarda `TELEGRAM_IMAGE_BATCH_WAIT_SECONDS`, default 2.5s), enviando como batch ao `MessageProcessor`
- `start_polling()`: inicia `Poller` em thread daemon
- `set_webhook(public_url)`: registra webhook no Telegram API
- `handle_telegram_update(update_json)`: ponto de entrada do webhook route

### `telegram_processor.py` — Pipeline de mensagens
Classe `MessageProcessor`:
1. Extrai update JSON via `MessageExtractor`
2. Resolve usuário via `UserLinker` (vincula chat_id → `Usuario`)
3. Cria/atualiza `Conversa` via `get_or_create_conversa` (session_service)
4. Registra `MensagemCampo` (idempotência via `hash_idempotencia`)
5. Monta config do agente: `actor_user_id`, `actor_level`, `tenant_id`, `obra_id_ativa`, `location_profile`, `thread_id`, `conversa_id`
6. Invoca `graph.invoke({"messages": [HumanMessage(...)]}, config)`
7. Envia resposta via `BotClient` (TypingIndicator ativo durante processamento)
8. Atualiza `ultima_msg_em` da conversa
- Comandos de reset: `/nova_thread`, `/reset`, `/limpar_contexto` → gera novo `thread_id`

### `diario_service.py` — Geração de diários
Função principal: `gerar_ou_regerar_diario(obra_id, tenant_id, tipo, data_inicio, data_fim, gerado_por, motivo_regeracao, include_pending)`

Fluxo:
1. `_get_registros_para_diario()`: busca registros APROVADO (+ PENDENTE se `include_pending`) no período; resolve registros com `obra_id=NULL` via `FrenteServico.obra_id`; usa `selectinload` para frentes e imagens
2. Renderiza conteúdo via `pdf_service.py` (ReportLab)
3. Upload para Supabase Storage via `utils/storage.py`
4. Cria ou atualiza `Diario` (unique constraint por obra+tipo+período); incrementa `versao_atual`
5. Cria `DiarioVersao` com versão, `storage_path`, `storage_url`, `registros_ids`, `include_pending`
6. Cria/atualiza `DiarioRegistro` (junção)
7. Retorna dict com dados do diário (inclui versões)

**Observação crítica**: o upload para Supabase Storage acontece dentro do bloco de transação do banco (I/O externo dentro de transação — ver seção 11).

### `pdf_service.py` / `excel_service.py` / `word_service.py`
- PDF: ReportLab, tabelas por frente de serviço, cabeçalho com obra/data, rodapé com versão
- Excel: openpyxl, planilha de registros + planilha de imagens embedadas
- Word: python-docx, tabela de registros + seção de imagens

### `session_service.py` — Memória vetorial
- `get_or_create_conversa(db, tenant_id, usuario_id, chat_id, thread_id)`: cria ou recupera `Conversa` aberta
- `atualizar_ultima_mensagem(db, conversa_id)`: atualiza `ultima_msg_em`
- `encerrar_conversa(db, conversa_id)`: seta `encerrada_em = now()`
- `buscar_memorias_relevantes(db, tenant_id, query)`: embeds a query, busca via cosine similarity no pgvector, retorna `resumo` das conversas mais similares

---

## 6. Gateway tools

### Arquitetura

O padrão Gateway centraliza todas as chamadas de ferramentas do agente em uma única camada com contratos bem definidos:

```
LLM (Gemini) → tool_call → gateway_tools.py → GatewayService → handler (database/*)
                                                       ↓
                                              GatewayPolicyService
                                              (assert_can_read/write/intent)
```

Seleção do modo: `AGENT_USE_GATEWAY=true` (env) → usa `get_gateway_tools`; false → `get_database_tools` (acesso direto ao DB).

### Contratos (`gateway/contracts.py`)

```python
ActorContext(actor_user_id: int, actor_level: str)

GatewayRequestMeta(operation, action_route, intent, business_tool, ...)

GatewayRequest(actor: ActorContext, meta: GatewayRequestMeta, payload: dict)

GatewayResponse(ok: bool, operation: str, data: dict, warnings: list)

WriteOptions(require_confirmation: bool = True, confirmed: bool = False)
```

### Políticas (`gateway/policies.py` — `GatewayPolicyService`)

| Método | Comportamento |
|--------|--------------|
| `assert_can_read` | Todos os 3 níveis podem ler |
| `assert_can_write` | Todos os 3 níveis podem escrever |
| `assert_can_manage_others` | Apenas Admin/Gerente |
| `assert_owner_or_manager` | Admin/Gerente ou próprio dono do dado |
| `assert_execution_intent` | Intent deve estar em `ALLOWED_EXECUTION_INTENTS` |

`ALLOWED_EXECUTION_INTENTS` (em `policies.py`): `registrar_producao`, `registrar_alerta`, `atualizar_registro`, `consolidar_registro`, `gerenciar_frente_servico`  
*(nota: `gerenciar_tipo_alerta` e `gerar_diario` estão em `gateway_tools.py` mas não em `policies.py` — ver seção 11)*

### Intents em `gateway_tools.py`

`ALLOWED_EXECUTION_INTENTS` (local, gateway_tools): `registrar_producao`, `registrar_alerta`, `atualizar_registro`, `consolidar_registro`, `gerenciar_frente_servico`, `gerenciar_tipo_alerta`, `gerar_diario`

`EXECUTION_INTENT_ALIASES`: normaliza variantes (ex: `"criar_registro"` → `"registrar_producao"`, `"consolidar"` → `"consolidar_registro"`)

### Tools expostas ao LLM

**Factory**: `get_gateway_tools(actor_user_id, actor_level, tenant_id, obra_id_ativa, location_profile)` — closure que injeta contexto do ator em cada tool.

Todas retornam `GatewayResponse.to_dict()` ou `GatewayError.to_dict()`.

**Tools de consulta (READ):**
1. `consultar_registro_operacional(registro_id)` — detalhe completo com imagens
2. `consultar_registros_por_obra(obra_id, data_inicio, data_fim)` — listagem paginada
3. `consultar_registros_por_frente(frente_id, data_inicio, data_fim)`
4. `consultar_frente_servico_operacional(frente_id_ou_nome)` — detalhe + encarregado
5. `listar_frentes_servico(obra_id)` — todas as frentes de uma obra
6. `consultar_schema_frente_servico(frente_id)` — `campos_ativos`, `campos_extras`, `campos_localizacao`
7. `consultar_diario_obra(diario_id)` — detalhe com versões
8. `listar_diarios_obra(obra_id, tipo)` — histórico de diários
9. `consultar_alertas_operacionais(status, severity, obra_id)` — lista filtrada
10. `consultar_alerta(alerta_id)` — detalhe
11. `consultar_usuario(usuario_id)` — nome, nível, telefone
12. `listar_usuarios_obra(obra_id)` — membros da obra
13. `consultar_producao_periodo(obra_id, data_inicio, data_fim)` — KPIs de produção
14. `sugerir_campos_faltantes(registro_id, dados_parciais)` — validação de completude via `BusinessRAGService`

**Tools de execução (WRITE — passam por `assert_can_write` + `assert_execution_intent`):**
15. `criar_registro_operacional(...)` — cria com status=pendente, intent: `registrar_producao`
16. `atualizar_registro_operacional(registro_id, ...)` — atualização parcial, intent: `atualizar_registro`
17. `consolidar_registro(registro_id)` — status = aprovado, intent: `consolidar_registro`
18. `rejeitar_registro(registro_id, motivo)` — status = rejeitado, intent: `consolidar_registro`
19. `anexar_imagem_registro(registro_id, image_url, ...)` — upload de imagem, intent: `atualizar_registro`
20. `criar_alerta(tipo, severity, title, description, ...)` — intent: `registrar_alerta`
21. `atualizar_status_alerta(alerta_id, novo_status, ...)` — intent: `registrar_alerta`
22. `marcar_alerta_lido(alerta_id)` — intent: `registrar_alerta`
23. `criar_frente_servico(obra_id, nome, encarregado_id)` — intent: `gerenciar_frente_servico`
24. `atualizar_frente_servico(frente_id, ...)` — intent: `gerenciar_frente_servico`
25. `deletar_frente_servico(frente_id)` — intent: `gerenciar_frente_servico`
26. `criar_tipo_alerta_alias(alias, canonical_type, descricao)` — intent: `gerenciar_tipo_alerta`
27. `atualizar_tipo_alerta_alias(alias_id, ...)` — intent: `gerenciar_tipo_alerta`
28. `deletar_tipo_alerta_alias(alias_id)` — intent: `gerenciar_tipo_alerta`
29. `gerar_diario_obra(obra_id, tipo, data_inicio, data_fim, include_pending)` — intent: `gerar_diario`

**Normalização de tipo de alerta** (`_normalize_alert_type_for_gateway`): converte texto livre (ex: "máquina quebrou", "colisão") para canonical values via tabela de aliases estáticos + fuzzy match com `difflib`.

**Tools Telegram** (`telegram_tools.py`):
- `enviar_mensagem_usuario`, `enviar_foto`, `criar_poll`, `encerrar_conversa_atual` — binding específico ao `chat_id` e `thread_id` da conversa atual

---

## 7. Configuração e ambiente

### `core/config.py` — Pydantic Settings

```python
class Settings(BaseSettings):
    google_api_key: str                    # Obrigatório
    telegram_token: str | None = None
    database_url: str                      # Obrigatório
    redis_url: str | None = None
    supabase_url: str | None = None
    supabase_service_key: str | None = None
    bot_channel: str = "telegram"
    whatsapp_access_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_verify_token: str | None = None
    whatsapp_app_secret: str | None = None
```

### Variáveis de ambiente (`.env` atual — ambiente dev)

| Variável | Valor/Status |
|----------|-------------|
| `GOOGLE_API_KEY` | Configurado (Gemini) |
| `GOOGLE_API_WEB_SEARCH_KEY` | Configurado |
| `DATABASE_URL` | PostgreSQL Supabase (pooler us-east-1:6543) |
| `TELEGRAM_TOKEN` | Configurado |
| `TELEGRAM_POLLING_IN_DEV` | `true` |
| `TELEGRAM_POLLING_DEBUG` | `false` |
| `TELEGRAM_TYPING_INDICATOR_ENABLED` | `true` |
| `TELEGRAM_TYPING_INTERVAL_SECONDS` | `3.5` |
| `TELEGRAM_IMAGE_BATCH_WAIT_SECONDS` | não definido (usa default 2.5) |
| `PUBLIC_BASE_URL` | `https://seu-servico.a.run.app` (placeholder) |
| `AUTH_SECRET_KEY` | `secret123key` (fraco — dev) |
| `OBRALOG_ENV` | `dev` |
| `CORS_ORIGINS` | `http://localhost:5173` |
| `FLASK_APP` | `backend.main` |
| `REDIS_URL` | `redis://localhost:6379` |
| `AGENT_USE_GATEWAY` | `true` |
| `LANGSMITH_TRACING` | `true` (projeto `dev-obralog`) |
| `SUPABASE_URL` | não configurado no `.env` lido |
| `SUPABASE_SERVICE_KEY` | não configurado no `.env` lido |

### `main.py` — Startup

1. Carrega blueprints (13 blueprints registrados)
2. Configura CORS: `r"/api/*"` e `r"/backend/uploads/*"` para origens de `CORS_ORIGINS`
3. Lógica de bot:
   - `BOT_CHANNEL=telegram`: dev-mode → polling em thread daemon; prod-mode → webhook via `PUBLIC_BASE_URL`
   - `BOT_CHANNEL=whatsapp`: apenas loga instruções, webhook passivo
4. Expõe `GET /health` e `GET /backend/uploads/registros/<filename>`
5. `__main__`: `app.run(host="0.0.0.0", port=5000, debug=True)`

### `db/session.py` — Banco de dados

- Engine: `pool_pre_ping=True`, `pool_size=3`, `max_overflow=2`
- Auto-normaliza `postgresql://` → `postgresql+psycopg://`
- Registra pgvector handler no `connect` event (graceful fallback se indisponível)
- **`ensure_runtime_migrations()`** chamado na importação do módulo: executa ~50 DDL statements idempotentes, cobrindo toda a evolução do schema desde o início do projeto

### `requirements.txt` — Dependências relevantes

```
Flask==3.1.3, SQLAlchemy==2.0.49, flask-cors==6.0.2
psycopg[binary]==3.3.3, pgvector>=0.3.0, asyncpg==0.31.0
langgraph==1.1.6, langgraph-checkpoint-postgres==3.0.5
langchain-core==1.2.26, langchain-google-genai==4.2.1
langchain-anthropic==1.4.0, anthropic==0.89.0
python-telegram-bot==22.7
reportlab>=4.0.0, openpyxl>=3.1.0, python-docx>=1.1.0
pydantic==2.12.5, pydantic-settings==2.13.1
redis==7.4.0, itsdangerous==2.2.0
fastapi==0.135.3, uvicorn==0.43.0, starlette==1.0.0 (instalados mas Flask é o server)
gunicorn==23.0.0, alembic==1.18.4 (instalado mas não usado como migrations primárias)
telegramify-markdown==1.1.3, langsmith==0.7.25
```

---

## 8. Jobs agendados

Os jobs são scripts Python standalone, sem scheduler interno. Precisam ser agendados externamente (cron do SO, APScheduler, Cloud Scheduler, etc.).

### `backend/jobs/gerar_diarios_diarios.py`

**Propósito**: Para cada tenant ativo, para cada obra ativa, se houver ao menos 1 registro aprovado para hoje, gera ou regera o diário do dia.

**Execução**: `python -m backend.jobs.gerar_diarios_diarios`

**Fluxo**:
1. Carrega todos `Tenant.ativo=True`
2. Para cada tenant, carrega `Obra.ativo=True`
3. Para cada obra, verifica `Registro` com `status=APROVADO` e `data=hoje`
4. Se existir: chama `gerar_ou_regerar_diario(obra_id, tenant_id, tipo="diario", data_inicio=hoje, data_fim=hoje, gerado_por=<primeiro admin do tenant>)`
5. Log de `"criado"` (versao==1) ou `"regerado"` (versao>1)
6. Erros por obra são capturados e logados individualmente (não interrompem o loop)

**Observação**: sem lock de idempotência — se executado duas vezes no mesmo dia para a mesma obra, regerará o diário duas vezes.

---

### `backend/jobs/encerrar_conversas.py`

**Propósito**: Encerra conversas que excederam o `timeout_conversa_minutos` do tenant.

**Execução**: `python -m backend.jobs.encerrar_conversas`

**Fluxo**:
1. Query SQL direta:
   ```sql
   SELECT c.id FROM conversas c
   JOIN tenants t ON t.id = c.tenant_id
   WHERE c.encerrada_em IS NULL
     AND c.ultima_msg_em < now() - (t.timeout_conversa_minutos || ' minutes')::interval
   ```
2. Para cada `conversa_id`, chama `encerrar_conversa(db, conversa_id)` (seta `encerrada_em`)
3. Erros por conversa são logados individualmente

**Observação**: sem lock de idempotência. Conversas são encerradas em sessões separadas, cada uma em `with SessionLocal()`.

---

## 9. Autenticação e multi-tenancy

### Autenticação

**Mecanismo**: JWT stateless via `itsdangerous.URLSafeTimedSerializer`.

- Payload: `{"sub": user_id, "email": email, "tenant_id": tenant_id}`
- Salt: `"obralog-auth"` (fixo no código)
- Expiração: `AUTH_TOKEN_MAX_AGE_SECONDS` (env, default 86400s = 24h)
- Chave: `AUTH_SECRET_KEY` (env, **fallback hardcoded** `"obralog-dev-secret"` se não definida)

**`require_auth` decorator**: decodifica token, valida `sub`, popula `g.current_user` (objeto `Usuario`) e `g.tenant_id`. Busca o usuário no banco a cada request.

**Validação de senha**: suporta hashes `pbkdf2:` e `scrypt:` via werkzeug, e plaintext para dev.

**Níveis de acesso** (RBAC manual via helpers):
- `_is_admin(user)` → `nivel_acesso == "administrador"`
- `_is_gerente_or_admin(user)` → nível ∈ `{administrador, gerente}`

### Multi-tenancy

**Isolamento**: toda query inclui `WHERE tenant_id = <tenant_id do token>`. Não há middleware automático — cada repository/route filtra manualmente.

**Tenant switching**: `POST /api/v1/admin/switch-tenant` (super-admin only) — muda `tenant_id` no contexto.

**Convites**: `UserInviteCode` com validade de 24h. O `nivel_acesso` do convite determina o nível do novo usuário.

**Vínculo Telegram**: `TelegramLinkCode` (gerado por admin, expira em `datetime(9999,12,31)` — sem expiração prática). O encarregado envia o código no chat para vincular seu `telegram_chat_id`.

### Contexto no agente

O `telegram_processor` monta o `config` do LangGraph com:
```python
{
    "configurable": {
        "thread_id": ...,       # ID do thread LangGraph (persistência)
        "actor_user_id": ...,
        "actor_level": ...,     # NivelAcesso.value
        "tenant_id": ...,
        "obra_id_ativa": ...,   # Obra padrão do usuário (UsuarioObra.eh_padrao)
        "location_profile": ...,# Tenant.location_type (estaca/km/texto)
        "telegram_chat_id": ...,
        "telegram_message_thread_id": ...,
        "conversa_id": ...,
        "actor_name": ...,
        "actor_chat_display_name": ...,
        "conversation_date": ...,
        "conversation_date_br": ...,
    }
}
```

---

## 10. Pontos de chamada LLM

### LLM principal — `agents/llms.py`

**Modelo**: `gemini-2.5-flash` via `ChatGoogleGenerativeAI` (`langchain-google-genai`)

```python
llm_main = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.environ["GOOGLE_API_KEY"],
)
```

**Embeddings**: `GoogleGenerativeAIEmbeddings` com fallback automático pelos modelos (em ordem):
1. `GOOGLE_EMBEDDING_MODEL` (env, default `models/text-multilingual-embedding-002`)
2. `models/text-multilingual-embedding-002`
3. `models/text-embedding-004`
4. `models/gemini-embedding-2-preview`
5. `models/gemini-embedding-001`
6. `models/embedding-001`
→ **768 dims** (modelo multilingual)

**Transcrição de áudio**: `transcribe_audio_bytes(audio_bytes, mime_type)` — envia áudio base64 para `llm_main` com instrução de transcrição pt-BR.

---

### Chamadas ao LLM (pontos de invocação)

**1. `agent_step` — nó principal do grafo** (`agents/nodes/response.py`)
- Invocado: toda mensagem recebida pelo bot
- Monta `SystemMessage` com: `build_system_prompt()` + bloco de contexto do usuário + perfil de localização + contexto RAG vetorial + memórias de conversas anteriores + sinais detectados na mensagem
- Se `actor_user_id` disponível: `llm_main.bind_tools(tools).invoke([system_message] + messages)`
- Se sem contexto de ator: `llm_main.invoke([system_message] + messages)` (sem tools)

**2. `tools_step` — execução de tools** (`agents/nodes/response.py`)
- Não invoca LLM diretamente
- Executa as tools solicitadas pelo LLM e retorna `ToolMessage` para cada uma
- Valida campos obrigatórios (`_ensure_required_fields`) antes de executar
- Normaliza output via `_normalize_tool_output` (enriquece com `faltantes`, `validacoes`, `next_steps`)

**3. RAG — `vector_context.py`** (`agents/context/vector_context.py`)
- Invocado: dentro de `_build_system_message`, para cada mensagem recebida
- Embeds a última mensagem humana via `embeddings_main.embed_query`
- Busca conversas similares via pgvector cosine similarity no tenant

**4. RAG de memórias — `session_service.py`** (`buscar_memorias_relevantes`)
- Invocado: dentro de `_build_system_message`, se `tenant_id` disponível
- Embeds a query, busca `resumo` das conversas mais similares (já encerradas)

**5. Transcrição de áudio — `llms.py`** (`transcribe_audio_bytes`)
- Invocado: pelo `MessageExtractor` quando a mensagem contém áudio
- Usa `llm_main.invoke` com conteúdo multimodal (media + text)

**6. SDK Anthropic** (`langchain-anthropic==1.4.0`, `anthropic==0.89.0`)
- Instalado e importado no requirements, mas **não há ponto de invocação ativo** identificado no código lido. O agente usa exclusivamente Gemini (`llm_main`).

---

### Grafo LangGraph (`agents/graph.py`)

```
START
  └─→ agent (agent_step)
           ├─→ [tool_calls presente] → tools (tools_step) → agent (loop)
           └─→ [sem tool_calls]      → END
```

- Checkpointer: `PostgresSaver` (LangGraph checkpoint postgres) — persiste histórico de mensagens por `thread_id` no PostgreSQL
- Grafo compilado com `checkpointer=checkpointer` — suporta multi-turn stateful

---

### System prompt (`agents/prompts.py`)

`SYSTEM_PROMPT_BASE` define:
- Linguagem: sempre pt-BR, Markdown simples Telegram
- Identidade: assistente de diário de obra da ObraLog
- Regras de coleta: criar registro parcial imediatamente, atualizar iterativamente, nunca criar dois registros no mesmo contexto
- Regras de aprovação: validar via `sugerir_campos_faltantes`, aprovar automaticamente quando pronto (sem confirmação explícita)
- Regras de localização: usar `consultar_schema_frente_servico` ao identificar nova frente; respeitar `campos_localizacao` do schema
- Intents permitidos: `registrar_producao`, `atualizar_registro`, `consolidar_registro`, `registrar_alerta`
- Sem inventar dados; sem expor IDs técnicos

Se `read_agent_instructions()` retornar conteúdo, anexa aviso de que há "instruções operacionais editáveis ativas" (mas não as inclui no prompt diretamente — o agente deve consultar via tools RAG).

---

## 11. Observações e inconsistências encontradas

1. **Divergência de `ALLOWED_EXECUTION_INTENTS` entre `policies.py` e `gateway_tools.py`**: `policies.py` lista 5 intents (`registrar_producao`, `registrar_alerta`, `atualizar_registro`, `consolidar_registro`, `gerenciar_frente_servico`), enquanto `gateway_tools.py` lista 7 (adiciona `gerenciar_tipo_alerta` e `gerar_diario`). Se `GatewayService.execute_execucao` for usado para tools com essas intents extras, `assert_execution_intent` falhará. Aparentemente as tools de tipo_alerta e gerar_diario não passam por `execute_execucao` com política de intent, mas isso não está explicitamente documentado.

2. **I/O externo (Supabase Storage) dentro da transação do banco** (`diario_service.py`): o upload do PDF para o Supabase ocorre antes do commit da transação SQLAlchemy. Se o commit falhar após o upload, o arquivo fica no storage sem referência no banco. Registrado como issue pendente em memória de projeto.

3. **Jobs sem lock de idempotência**: `gerar_diarios_diarios.py` e `encerrar_conversas.py` não implementam locks distribuídos. Execuções concorrentes (ex: se o scheduler disparar duas vezes) podem causar dupla geração de versões ou race condition no encerramento de conversas.

4. **`AUTH_SECRET_KEY` com fallback hardcoded**: `_AUTH_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY") or "obralog-dev-secret"`. Se a variável não for definida em produção, tokens gerados com a chave fraca serão aceitos. A versão atual no `.env` usa `secret123key` (ainda fraco para produção).

5. **`signed URL` armazenada em `DiarioVersao.storage_url` pode expirar**: Supabase signed URLs têm TTL. O valor armazenado não é permanentemente válido. Mitigação na UI: sempre busca URL fresca ao servir o PDF (não usa o valor cached do banco).

6. **Rate limiting ausente em `/api/v1/auth/login`**: endpoint sem proteção contra força bruta.

7. **`Alembic` instalado mas não usado como mecanismo primário de migração**: todas as migrações são feitas via `ensure_runtime_migrations()` em `session.py`. `alembic==1.18.4` está no requirements, mas não há pasta `alembic/` no projeto. Pode ser um remanescente de dependência ou plano futuro.

8. **`FastAPI`, `Starlette`, `uvicorn` instalados mas a aplicação usa Flask**: os três estão no `requirements.txt` e são instalados, mas o framework ativo é Flask/Werkzeug. Provável overhead de instalação sem uso.

9. **`Redis` instalado mas não em uso pleno**: `redis==7.4.0` presente no requirements; `REDIS_URL` definida no `.env`, mas não foi identificado ponto de uso ativo no código lido (sem cache, sem filas, sem pub/sub ativos).

10. **`Anthropic SDK` instalado mas não usado no agente**: `anthropic==0.89.0` e `langchain-anthropic==1.4.0` estão instalados e importados no requirements, mas o agente usa exclusivamente Gemini (`llm_main`). Pode ser infraestrutura para uso futuro ou experimento pendente.

11. **Campo `tipo_obra` (texto) em `Obra` e `RegistroSchema` coexiste com `tipo_obra_id` (FK)**: há dois campos para o mesmo conceito — o campo texto `tipo_obra` parece ser legado e `tipo_obra_id` é o FK normalizado. Não há constraint garantindo consistência entre os dois.

12. **`TelegramLinkCode.expires_at` = `datetime(9999,12,31)` (sem expiração prática)**: documentado em `auth.py` como `_NON_EXPIRING_LINK_CODE_EXPIRES_AT`. O campo existe mas não é checado efetivamente para esses códigos. Não é bug, mas pode confundir quem lê o modelo esperando que todos os `link_codes` expirem.

13. **`notifications.py` é placeholder vazio**: importado em alguns pontos mas não implementado. Nenhuma notificação por email/SMS está ativa.

14. **Pasta de uploads local** (`/backend/uploads/registros/`): imagens de registros são salvas no sistema de arquivos do servidor, não em storage externo (diferente dos PDFs que vão para Supabase). Em ambiente containerizado/stateless, essas imagens se perdem no restart.

15. **`diario_v1` (singular) e `diarios_v1` (plural) coexistem no mesmo arquivo `diario.py`**: três blueprints distintos (`router`, `diarios_router`, `diarios_files_router`). `diario_v1` contém endpoints legados; `diarios_v1` contém o novo CRUD. Ambos registrados em `main.py`.
