# ObraLog — Análise Crítica do Sistema

> Gerado em: 2026-05-21  
> Nível: Engenharia sênior — pronto para sprint planning

---

## 1. Falhas de Segurança

### 🔴 CRÍTICO — Cross-Tenant em `finalizar_diario`

**Arquivo:** `backend/services/diario_service.py:222`

```python
# BUG: sem filtro de tenant_id
diario = db.query(Diario).filter(Diario.id == diario_id).first()
```

Um usuário autenticado em qualquer tenant pode finalizar o diário de outro tenant se souber o UUID. O UUID é um identificador forte mas não é segredo — aparece em responses da API.

**Correção:** Passar e filtrar por `tenant_id`:
```python
def finalizar_diario(diario_id: str, finalizado_por: int, tenant_id: int) -> dict:
    diario = db.query(Diario).filter(
        Diario.id == diario_id,
        Diario.tenant_id == tenant_id,  # obrigatório
    ).first()
```

A rota também precisa passar `tenant_id=g.tenant_id` ao chamar o serviço.

---

### 🔴 CRÍTICO — Auth secret key pode ser o GOOGLE_API_KEY

**Arquivo:** `backend/api/routes/auth.py:19`

```python
_AUTH_SECRET_KEY = (
    os.environ.get("AUTH_SECRET_KEY")
    or os.environ.get("GOOGLE_API_KEY")
    or "obralog-dev-secret"
)
```

Se `AUTH_SECRET_KEY` não estiver definida, a secret de tokens JWT recai sobre a `GOOGLE_API_KEY`. Quem conhece a chave do Google (exposta em logs, dashboards de billing, etc.) consegue forjar tokens.

**Correção:** Remover o fallback para `GOOGLE_API_KEY`. Usar apenas `AUTH_SECRET_KEY` ou abortar o boot se não estiver definida em produção.

---

### 🟠 ALTO — Ausência de rate limiting nos endpoints de autenticação

**Arquivo:** `backend/api/routes/auth.py` — `/login`, `/register`

Não há proteção contra brute force em `/login`. Com ~86.400 tentativas por dia (limite do token), é possível atacar senhas fracas.

**Correção:** Adicionar rate limiting por IP e por email (Flask-Limiter ou NGINX). Bloquear conta após N falhas.

---

### 🟠 ALTO — Signed URL armazenada em banco pode estar expirada

**Arquivo:** `backend/db/models.py` — `DiarioVersao.storage_url`

O campo `storage_url` é preenchido no momento da geração com uma signed URL de 1h. Qualquer leitura posterior à expiração retorna uma URL inválida silenciosamente. O frontend que use `storage_url` diretamente terá acesso quebrado.

**Correção:** Nunca armazenar a signed URL no banco. Sempre gerá-la sob demanda via `GET /diarios/:id/versoes/:v/url`. Remover ou marcar o campo `storage_url` como deprecated.

---

### 🟡 MÉDIO — CORS com domínio hardcoded em desenvolvimento

**Arquivo:** `backend/main.py:44`

```python
raw_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
```

Em produção, se `CORS_ORIGINS` não for definida, o CORS aceita apenas `localhost:5173`, bloqueando o frontend real. O oposto — definir `*` por acidente — abre o sistema para qualquer origem.

**Correção:** Tornar `CORS_ORIGINS` obrigatória em produção. Validar formato no boot.

---

### 🟡 MÉDIO — `photo_urls` de alertas sem validação de domínio

**Arquivo:** `backend/api/routes/alerts.py` — campo `photo_urls` (lista de strings)

URLs de foto são aceitas sem validação. Se o backend algum dia buscar essas URLs (para preview ou re-upload), há risco de SSRF.

**Correção:** Validar que as URLs são do Supabase Storage ou outro domínio confiável antes de persistir.

---

### 🟡 MÉDIO — Token não invalida ao trocar de tenant

**Arquivo:** `backend/api/routes/auth.py`, `backend/api/routes/admin.py`

O `tenant_id` está embutido no JWT. Ao fazer tenant switching via `/admin/switch-tenant`, um novo token é emitido, mas o token antigo (com o tenant anterior) ainda é válido por até 86.400s.

**Correção:** Implementar revogação de token (blacklist em Redis) ou reduzir TTL e usar refresh tokens.

---

## 2. Falhas de Lógica de Negócio

### 🔴 CRÍTICO — `diario_registros` perde rastreabilidade de versões

**Arquivo:** `backend/services/diario_service.py:152`

```python
db.query(DiarioRegistro).filter(DiarioRegistro.diario_id == diario.id).delete()
for r in registros:
    db.add(DiarioRegistro(diario_id=diario.id, ...))
```

A tabela `diario_registros` sempre reflete a versão **atual**, mas não qual versão cada registro pertencia. O `DiarioVersao.registros_ids` (JSONB) captura isso por versão, porém é duplicação de dado e a fonte de verdade fica inconsistente: se `registros_ids` e `diario_registros` divergem, qual prevalece?

**Correção:** Ou (a) adicionar `versao` à tabela `diario_registros` para rastrear histórico, ou (b) remover `diario_registros` e usar apenas o JSONB em `diario_versoes`.

---

### 🟠 ALTO — Frentes de serviço desvinculadas de obras

**Arquivo:** `backend/db/models.py:278`

```python
obra_id = Column(Integer, ForeignKey("obras.id", ondelete="SET NULL"), nullable=True)
```

`FrenteServico.obra_id` é nullable. Registros podem ser criados vinculados a uma frente que não pertence à obra do registro. Não há constraint de integridade cruzada entre `registros.obra_id` e `registros.frente_servico_id → frentes_servico.obra_id`.

**Correção:** Adicionar constraint no banco ou validação no service: frente deve pertencer à obra do registro.

---

### 🟠 ALTO — Job cron sem mecanismo de lock/idempotência

**Arquivo:** `backend/jobs/gerar_diarios_diarios.py`

Se o job for executado duas vezes simultaneamente (falha de deploy, cron duplicado), dois processos tentarão gerar/regrerar o mesmo diário ao mesmo tempo. O `UNIQUE(obra_id, tipo, data_inicio, data_fim)` previne inserção dupla, mas podem ocorrer race conditions no `versao_atual++` e no upload paralelo ao storage.

**Correção:** Adicionar lock de aplicação (Redis SETNX) ou lock de banco (`SELECT ... FOR UPDATE`) antes de gerar.

---

### 🟡 MÉDIO — Registro com `data` nullable

**Arquivo:** `backend/db/models.py:317`

```python
data = Column(Date, nullable=True, index=True)
```

O campo `data` de um registro pode ser NULL. Um registro sem data não pode ser incluído em nenhum diário (o filtro por período é por `data >= data_inicio`), gerando registros "perdidos" invisíveis para o sistema.

**Correção:** Tornar `data` NOT NULL ou tratar explicitamente registros sem data no fluxo de aprovação.

---

### 🟡 MÉDIO — Status do diário não protege contra regeneração após aprovação

O spec define que regerar após finalizado volta para rascunho. Mas não há proteção para um ENCARREGADO solicitar via agente a regeração de um diário já finalizado por um engenheiro. A tool `gerar_diario_obra` no gateway usa a policy do ator, mas a policy não distingue entre "criar rascunho" e "regrerar finalizado".

**Correção:** Verificar no serviço/gateway se o diário está finalizado e exigir nível mínimo (gerente) para regenerar.

---

### 🟡 MÉDIO — `gerado_por` no job usa primeiro admin do tenant

**Arquivo:** `backend/jobs/gerar_diarios_diarios.py:88`

```python
user = db.query(Usuario).filter(
    Usuario.tenant_id == tenant_id,
    Usuario.nivel_acesso == NivelAcesso.ADMINISTRADOR,
).first()
```

O job atribui o diário gerado automaticamente ao primeiro admin encontrado (ordenação implícita), sem critério. Em tenants com múltiplos admins, isso cria registros de auditoria enganosos.

**Correção:** Criar um usuário "sistema" por tenant ou usar NULL com flag `gerado_automaticamente`.

---

## 3. Pontos Críticos de Código (Refatoração)

### 🔴 `diario.py` — arquivo com responsabilidades misturadas (450 linhas)

**Arquivo:** `backend/api/routes/diario.py`

O arquivo mistura:
- Endpoints legados (diário-do-dia sem persistência, `/diario/dia`, `/diario/periodo`)
- Endpoints novos (diários persistidos com versionamento, `/diarios/gerar`)
- Helpers de serialização (`_registro_to_schema`, `_build_diario_do_dia_payload`)

Isso torna difícil manter os dois sistemas separados e rastrear bugs.

**Correção:** Separar em `diario_legado.py` (rotas `/diario/*`) e `diario_v2.py` (rotas `/diarios/*`).

---

### 🔴 Dois arquivos de schema duplicados e divergentes

**Arquivos:**
- `backend/api/schemas_diario.py` (mais completo — tem `localizacao`, `LocalizacaoSchema`)
- `backend/api/schemas/diario.py` (mais antigo — `estaca_inicial` e `resultado` são obrigatórios, divergindo da realidade)

O arquivo `api/routes/diario.py` importa de `schemas_diario.py` (correto), mas `api/schemas/diario.py` existe como código morto com campos inconsistentes que podem confundir futuros devs.

**Correção:** Deletar `api/schemas/diario.py`.

---

### 🔴 Sessão de banco aberta durante I/O externo (PDF + Storage)

**Arquivo:** `backend/services/diario_service.py:92`

A função `gerar_ou_regerar_diario` abre uma `SessionLocal()` e mantém a conexão aberta durante:
1. Geração do PDF (CPU-bound, potencialmente lento)
2. Upload para Supabase Storage (I/O de rede, 30s timeout)

Isso segura uma conexão do pool por toda a duração da operação. Com pool limitado, pode causar starvation.

**Correção:** Coletar os dados do banco, fechar a sessão, gerar o PDF e fazer upload, depois abrir nova sessão para persistir o resultado.

---

### 🟠 Repository pattern inconsistente

Algumas rotas usam `Repository.*` (padrão):
```python
frentes = Repository.frentes_servico.listar(db)
```

Outras acessam models diretamente nas rotas:
```python
q = db.query(Diario).filter(...)
```

Isso cria dois padrões de acesso coexistindo, sem critério claro de quando usar qual.

**Correção:** Mover queries de Diario da rota para o `DiarioRepository` ou `diario_service.py`.

---

### 🟠 `asyncpg` instalado mas código é 100% síncrono

**Arquivo:** `backend/requirements.txt` — `asyncpg==0.31.0`, `asyncio`, `fastapi`

O backend usa Flask síncrono com SQLAlchemy síncrono. `asyncpg` está instalado mas não é usado. `fastapi` também está instalado mas não há nenhum endpoint FastAPI. Isso aumenta o peso do ambiente sem benefício.

---

### 🟡 `Conversa.id` como BigInteger abre risco de colisão com IDs do Telegram

**Arquivo:** `backend/db/models.py` — `Conversa.id = Column(BigInteger, ...)`

Se `id` for o `chat_id` do Telegram, há semântica dupla (PK + identificador externo). Se for autoincrement, então é redundante com `chat_id`. A intenção não está clara no código.

---

### 🟡 Ausência de schemas Pydantic para os novos endpoints de diário

Os endpoints `POST /diarios/gerar` e `POST /diarios/:id/finalizar` fazem parsing manual de JSON:
```python
data = request.get_json(silent=True) or {}
obra_id = int(data["obra_id"])
```

Isso não gera documentação automática nem valida tipos automaticamente. Pydantic já está no projeto.

**Correção:** Criar `GerarDiarioRequest`, `DiarioResponse`, `DiarioVersaoResponse` em `schemas_diario.py` e usar no parsing.

---

## 4. Melhorias de UX e UI

### Frontend

| Prioridade | Item | Descrição |
|---|---|---|
| 🔴 Alta | Feedback de geração de PDF | A geração de PDF pode levar alguns segundos. O botão "Gerar Diário" deveria mostrar spinner e bloquear duplo clique |
| 🔴 Alta | URL de PDF expirada | O frontend pode guardar em cache uma signed URL expirada. Deve sempre buscar via `GET /versoes/:v/url` |
| 🟠 Média | Paginação em `/diarios` | Projetos longos acumulam muitos diários. Sem paginação, a listagem pode ser lenta |
| 🟠 Média | Histórico de versões visível | A `DiarioObraVisualizacaoPage` deve mostrar versões anteriores com motivo de regeração |
| 🟠 Média | Status do diário no Dashboard | O dashboard não exibe se há diários pendentes de finalização |
| 🟡 Baixa | Preview inline de PDF | Em vez de abrir em nova aba, exibir iframe do PDF na própria página |
| 🟡 Baixa | Notificação de diário gerado | Alertar gerentes quando o cron gera um diário automaticamente |
| 🟡 Baixa | Filtro de diários por status | A página de diários não tem filtro visual por status (rascunho/finalizado) |

### Mobile / Telegram

| Prioridade | Item |
|---|---|
| 🟠 Média | O agente não mostra preview do diário (apenas a URL). Enviar resumo textual junto com a URL |
| 🟠 Média | Sem feedback quando o diário falha a gerar (PDF ou storage offline). O agente retorna erro técnico crú |

---

## 5. Melhorias de Arquitetura (Médio/Longo Prazo)

### Migrar para async

O stack atual (Flask síncrono + pool de threads) não escala bem para operações I/O intensas como upload de PDF. Migrar para **FastAPI + asyncpg** (já instalados) melhoraria throughput sem aumento de custo.

### Event-driven para diários

Em vez do cron "pesquisar todos os tenants", usar eventos:
- `registro.aprovado` → pub/sub → `gerar_diario_se_necessario`

Isso elimina latência do cron e processa apenas o necessário.

### Separar storage de diários por tenant

O bucket `diarios` é único. Considerar buckets por tenant ou prefix policies do Supabase para isolamento de billing e quota.

### Webhook Telegram → queue

O processamento de mensagens do Telegram é síncrono dentro do webhook. Mensagens com foto (que requerem download + transcrição) bloqueiam o handler. Adicionar uma fila (Redis Queue ou similar) tornaria o webhook O(1).

---

## 6. Resumo de Ações Prioritárias

| # | Severidade | Ação | Arquivo |
|---|---|---|---|
| 1 | 🔴 Segurança | Adicionar `tenant_id` em `finalizar_diario` | `diario_service.py` + `diario.py` |
| 2 | 🔴 Segurança | Remover fallback de `AUTH_SECRET_KEY` para `GOOGLE_API_KEY` | `auth.py` |
| 3 | 🔴 Código | Deletar `api/schemas/diario.py` (duplicata divergente) | — |
| 4 | 🔴 Código | Separar I/O externo (PDF/Storage) da transação de banco | `diario_service.py` |
| 5 | 🟠 Segurança | Adicionar rate limiting em `/login` | `auth.py` |
| 6 | 🟠 Lógica | Lock de idempotência no job cron | `gerar_diarios_diarios.py` |
| 7 | 🟠 Código | Adicionar schemas Pydantic para endpoints de diários | `schemas_diario.py` |
| 8 | 🟠 Código | Mover queries de Diario para repository/service (sem acesso direto na rota) | `diario.py` |
| 9 | 🟡 UX | Feedback de carregamento no botão "Gerar Diário" | `DiarioObraPage.jsx` |
| 10 | 🟡 UX | Buscar signed URL sempre on-demand (nunca cachear) | `diarioService.js` |
