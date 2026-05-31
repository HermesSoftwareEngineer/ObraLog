# Documentacao — ObraLog

Documentacao tecnica, operacional e de referencia para o projeto ObraLog.

---

## Indice

### Sistema e Arquitetura

| Documento | Descricao |
|-----------|-----------|
| **[MAPEAMENTO_SISTEMA.md](./MAPEAMENTO_SISTEMA.md)** | Mapeamento completo: modelos, rotas, agente, gateway, jobs e observacoes tecnicas |
| **[ANALISE_CRITICA.md](./ANALISE_CRITICA.md)** | Falhas de seguranca, logica e codigo — acoes prioritarias para sprint |

### API e Integracao

| Documento | Descricao |
|-----------|-----------|
| **[../API_MAPEAMENTO.md](../API_MAPEAMENTO.md)** | Referencia completa de todos os endpoints REST com payloads |
| **[../CHANGELOG.md](../CHANGELOG.md)** | Historico cronologico de alteracoes |
| **[api-changes/README.md](./api-changes/README.md)** | Indice de alteracoes por data |
| **[api-changes/STATUS_ENDPOINTS.md](./api-changes/STATUS_ENDPOINTS.md)** | Status atual de cada endpoint |

### Operacao e Debug

| Documento | Descricao |
|-----------|-----------|
| **[DEBUG_TELEGRAM.md](./DEBUG_TELEGRAM.md)** | Guia de debug dos logs do bot Telegram (padroes, checklist, ativacao) |
| **[../README_TELEGRAM.md](../README_TELEGRAM.md)** | Setup e operacao do bot (polling e webhook) |
| **[../SETUP_DB.md](../SETUP_DB.md)** | Inicializacao e setup do banco de dados |

### Banco de Dados

O schema completo de todas as entidades esta em **[MAPEAMENTO_SISTEMA.md](./MAPEAMENTO_SISTEMA.md)** — secao 3 (Modelos de Dados).

As migracoes SQL ficam em `backend/db/migrations/sql/` (formato `YYYYMMDD_NNN_descricao.up/down.sql`).

---

## Arquivo Historico

Documentos de sprint e versoes anteriores estao em `archive/`:

| Pasta/Arquivo | Conteudo |
|---------------|----------|
| `archive/DB_DESENHO_TECNICO_20260414.md` | Desenho tecnico do banco da sprint de abr/2026 |
| `archive/GATEWAY_ROLLOUT.md` | Plano de rollout gradual do gateway (concluido) |
| `archive/IMPLEMENTACAO_ALERTS_ALERT_READS.md` | Plano de implementacao de alertas (concluido) |
| `archive/agente/PROMPT_AGENT_DIARIO.md` | Prompt completo do agente — versao anterior |
| `archive/agente/CONTEXTO_E_MEMORIA_AGENTE.md` | Tecnico de contexto/memoria — versao anterior |
| `archive/agente/MEMORY_PROMPT_AGENTE.md` | Formato de memoria para reinsercao — versao anterior |
| `archive/agente/GUIA_RAPIDO_AGENTE.md` | Resumo executivo do agente — versao anterior |

> Os docs do agente em `archive/agente/` descrevem uma versao anterior do sistema.
> A implementacao atual usa LangGraph + PostgresSaver (checkpoint automatico) + pgvector.
> O prompt ativo esta em `backend/agents/prompts.py` e as instrucoes editaveis em
> `backend/agents/context/padroes_operacionais_encarregado.md`.

---

## Estrutura de arquivos

```
ObraLog/docs/
├── README.md                        <- Este indice
├── MAPEAMENTO_SISTEMA.md            <- Referencia tecnica viva do sistema
├── ANALISE_CRITICA.md               <- Bugs, seguranca e acoes prioritarias
├── DEBUG_TELEGRAM.md                <- Debug do bot Telegram
├── api-changes/
│   ├── README.md
│   ├── STATUS_ENDPOINTS.md
│   ├── 20260405_alteracoes_frente_registros.md
│   ├── 20260414_api_frontend_lancamentos_mensagens.md
│   ├── 20260424_chat_conversas_mensagens.md
│   ├── 20260429_alertas_payload_simplificado.md
│   ├── 20260501_022_unidade_invite_codes.md
│   └── 20260501_gateway_tenant_localizacao.md
└── archive/
    ├── DB_DESENHO_TECNICO_20260414.md
    ├── GATEWAY_ROLLOUT.md
    ├── IMPLEMENTACAO_ALERTS_ALERT_READS.md
    └── agente/
        ├── PROMPT_AGENT_DIARIO.md
        ├── CONTEXTO_E_MEMORIA_AGENTE.md
        ├── MEMORY_PROMPT_AGENTE.md
        └── GUIA_RAPIDO_AGENTE.md
```
