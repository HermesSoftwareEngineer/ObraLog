# 2026-05-01 - Gateway do Agente com Contexto Multi-tenant e Localizacao Dinamica

## Resumo
Esta mudanca evolui o gateway/tools do agente para operar por tenant e adaptar coleta/validacao de localizacao por perfil (`estaca`, `km`, `texto`).

## Runtime Context (graph config)
O `configurable` enviado ao grafo agora inclui:
- `tenant_id`
- `obra_id_ativa` (hint de runtime; atualmente opcional)
- `location_profile`
- `location_labels`
- `location_required_fields`

Origem desses dados:
- `tenant_id` vem do usuario autenticado no fluxo Telegram.
- `location_profile` e campos de local sao resolvidos com base no `Tenant.location_type`.

## Comportamento por perfil
- Perfil `estaca`:
  - obrigatorios de local: `estaca_inicial`, `estaca_final`
  - agente pergunta valores inicial/final de estaca.
- Perfil `km`:
  - obrigatorios de local: `km_inicial`, `km_final`
  - agente pergunta km inicial/final.
  - valores sao normalizados para aliases legados de armazenamento (`estaca_inicial`, `estaca_final`).
- Perfil `texto`:
  - obrigatorio de local: `local_descritivo`
  - agente pergunta local descritivo.

## Compatibilidade legada
- `estaca_inicial` e `estaca_final` continuam aceitos.
- Payload estruturado `localizacao` tambem e aceito para criar/atualizar registro.
- Gateway faz normalizacao interna entre payload legado e dinamico.

## Checklist dinamico
A tool `sugerir_campos_faltantes` agora considera:
- perfil de localizacao ativo
- tenant/obra da conversa
- validacoes de referencia (frente/usuario) no escopo do tenant

## Isolamento por tenant
As tools internas de banco para usuarios, frentes, registros, mensagens, alertas e tipos de alerta passaram a usar escopo de tenant nas consultas e gravacoes.

## Arquivos principais alterados
- `backend/services/telegram_processor.py`
- `backend/agents/nodes/response.py`
- `backend/agents/gateway/rag_service.py`
- `backend/agents/gateway/location_profile.py`
- `backend/agents/tools/gateway_tools.py`
- `backend/agents/tools/database_tools.py`
- `backend/agents/tools/database/*.py`

## Testes adicionados/atualizados
- `backend/agents/tools/test_gateway_intents.py`
- `backend/agents/gateway/test_rag_user_instructions.py`
