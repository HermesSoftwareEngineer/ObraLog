# agent.md — ObraLog Backend

## Sobre o projeto

ObraLog é um SaaS multi-tenant de gestão de obras de infraestrutura (estradas,
pavimentação). Encarregados de campo enviam registros diários via Telegram ou
WhatsApp para um agente de IA (LangGraph), que os interpreta e persiste no banco.
Gestores acessam dashboards, diários de obra e alertas via interface web React.

Este arquivo cobre o backend em `ObraLog/backend/`.
O frontend está documentado em `ObraLogFront/agent.md`.

## Stack

Python 3.11+, Flask, SQLAlchemy 2.x (driver psycopg), LangGraph, LangChain Core,
PostgreSQL no Supabase com extensão `pgvector`, Telegram Bot API, WhatsApp webhook,
LLM externo (OpenAI/Anthropic)

## Banco de dados e migrações

### Modelos
- Todos os modelos herdam de `Base` (`DeclarativeBase`) em `backend/db/models.py`
- `tenant_id` é obrigatório em **toda** tabela nova: `ForeignKey("tenants.id")` +
  `nullable=False` + `index=True`
- ENUMs Python mapeados com `SQLEnum(..., values_callable=_enum_values)` — nunca
  omitir o `values_callable`, caso contrário gera conflito de tipo no PostgreSQL
- PKs: inteiros sequenciais para tabelas principais; UUID (`PGUUID(as_uuid=True)`)
  para entidades que circulam entre sistemas (alertas, mensagens, diários)

### Migrações
- **Toda** alteração de schema requer arquivo de migração SQL — nunca altere o
  banco sem uma
- Nomenclatura: `YYYYMMDD_NNN_descricao_snake_case.up.sql` e `.down.sql`
  - `NNN` = próximo número sequencial global (verificar a última migração)
  - Exemplo: `20260605_047_add_campo_x_to_obras.up.sql`
- Sempre criar `.down.sql` correspondente (mesmo que `-- rollback não suportado`)
- Aplicação: **manual** pelo dev no SQL Editor do Supabase, em ordem crescente
- Após criar a migração, atualizar o modelo em `models.py` para refletir a mudança

## Backend

### Rotas e blueprints
- Blueprints em `backend/api/routes/`, prefixo `/api/v1/<domínio>`
- Toda rota privada usa `@require_auth` — sem exceções sob `/api/v1/*`
- Endpoints sem auth são aceitáveis apenas em: `/telegram/*`, `/whatsapp/*`
  (webhooks externos autenticados pelo protocolo do canal), `/health`, `/`
- Registrar novo blueprint em `main.py` após criá-lo

### Padrão de response
```python
# Sucesso
return jsonify({"ok": True, "dados": ...}), 200

# Erro do cliente (validação, not found, conflito)
return jsonify({"ok": False, "error": "Mensagem clara"}), 400 | 404 | 409

# Erro inesperado
logger.error("contexto do erro: %s", exc)
return jsonify({"ok": False, "error": "Erro interno. Tente novamente."}), 500
```

### Isolamento de tenant
- **Nunca** consultar o banco sem filtrar por `tenant_id`
- Sempre usar `Repository` — nunca `db.query(Model)` diretamente em rotas
- `tenant_id` vem de `g.tenant_id` (injetado pelo `@require_auth` via JWT)
- Em SQL raw (jobs/scripts): sempre incluir `WHERE tenant_id = :tenant_id`

### O que é proibido em rotas
- Lógica de negócio complexa — delegue para `services/`
- Acesso direto ao banco sem `Repository`
- Consultas sem filtro de `tenant_id`
- Deixar exceções não capturadas propagarem para o Flask

### Tratamento de erro
- Erros esperados (validação, not found, conflito): capturar e retornar response
  adequada
- Erros inesperados: capturar com `try/except Exception as exc`, logar com
  `logger.error(...)`, retornar 500
- Nunca expor stack trace ou detalhes internos na response

## Agente IA

O agente do sistema é o bot Telegram/WhatsApp implementado com LangGraph
(`backend/agents/`). Não confundir com o Claude Code (agente de desenvolvimento).

### Arquitetura
- Grafo ReAct: `START → agent → tools → agent → ... → END`
- Contexto do ator propagado via `RunnableConfig["configurable"]`:
  `actor_user_id`, `actor_level`, `tenant_id`, `obra_id_ativa`
- Tools criadas por `get_gateway_tools()` — contexto capturado em closure,
  não passado por argumento em cada invocação

### Acesso ao banco
Tools do agente **sempre** chamam services (`backend/services/`). Nunca abrir
`SessionLocal()` diretamente em um handler de tool, nunca SQL raw, nunca acessar
`Repository` diretamente de dentro de uma tool.

Se não existe um service para a operação desejada, criar um em `backend/services/`
antes de implementar a tool.

> O código atual contém acesso via `_invoke_internal` → `database_tools` →
> `Repository` em muitas tools. Isso é débito técnico a ser corrigido
> progressivamente — o padrão correto é sempre via service.

### Sistema de créditos
Custos em `credito_service.CUSTO_OPERACOES`:
- `mensagem_agente`: 2 créditos — debitado no `agent_node` a cada turno do LLM
- `gerar_diario`: 10 créditos — debitado pelo `diario_service`
- `resumo_conversa`: 3 créditos

Regras:
- Débito sempre via `debitar_creditos(db, tenant_id, operacao)` — nunca
  manipular `TenantAssinatura` diretamente
- Saldo insuficiente: responder ao usuário com a mensagem padrão abaixo e não
  processar a operação
- Tenant sem assinatura: `verificar_saldo()` retorna `True` (não bloquear)

**Mensagem padrão para saldo insuficiente:**
> "Você atingiu o limite de créditos disponíveis. Para continuar, o
> administrador pode adicionar créditos avulsos ou aguardar a renovação mensal."

### O que o agente pode e não pode fazer

**Pode:**
- Criar, editar e deletar registros de produção
- Criar, editar e deletar alertas operacionais
- Gerar diários de obra
- Consultar qualquer dado do tenant ativo
- Consultar frentes de serviço e schemas de registro (somente leitura)

**Nunca pode:**
- Criar, editar ou deletar frentes de serviço (apenas tools de consulta)
- Criar, editar ou deletar schemas de registro (apenas tools de consulta)
- Criar ou deletar usuários
- Alterar senhas
- Deletar obras ou tenants do banco (pode desativar via `ativo=false`)
- Acessar dados de outro tenant
- Executar SQL raw
- Alterar planos ou assinaturas

## Jobs e cron

### Estrutura de um job
```python
# backend/jobs/nome_do_job.py
"""Descrição do job."""
import logging, sys
logger = logging.getLogger("obralog.jobs.nome_do_job")

def run() -> None:
    from backend.db.session import SessionLocal  # import lazy, dentro do run()
    ...

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    run()
```

### Registro
- Jobs contínuos: thread daemon registrada no `main.py` (ver padrão de
  `encerrar_conversas`)
- Jobs periódicos: cron externo executando `python -m backend.jobs.nome_do_job`
- Nomear arquivo em snake_case; logger com prefixo `obralog.jobs.<nome>`

## Testes

### Estrutura
```
backend/
  tests/
    unit/         ← funções puras: parsers, mappers, utilitários
    integration/  ← precisam do banco real de teste
    conftest.py   ← fixtures compartilhadas (SessionLocal de teste, tenant seed)
```

- Rodar com `pytest backend/tests/`
- Testes de integração só executam se `TEST_DATABASE_URL` estiver definido
- Criar testes quando a lógica for complexa — não obrigatório para todo endpoint
- Não mockar o banco em testes de integração — usar banco real de teste isolado

## Regras gerais de desenvolvimento

### Tamanho de tarefa e PR
- Preferência por PRs pequenos e focados (1 feature ou 1 fix por vez)
- PRs maiores são aceitos quando as mudanças são fortemente relacionadas
- Se o escopo crescer durante a implementação: parar, mapear o que foi
  descoberto, informar ao usuário e aguardar decisão (continua no mesmo PR,
  abre um segundo, ou vira tarefa futura)

### Contradições no código
- Nunca padronizar silenciosamente — sempre perguntar ao usuário antes
- Se a decisão for recorrente, documentar aqui no agent.md

### Comportamento padrão
- Comunicar em português (pt-BR)
- Nunca fazer commit sem solicitação explícita
- Nunca fazer push sem confirmação
- Não criar arquivos `.md` de documentação salvo quando explicitamente pedido
- Sempre ler o arquivo antes de editá-lo
- Antes de iniciar qualquer tarefa não trivial, confirmar o escopo com o usuário
