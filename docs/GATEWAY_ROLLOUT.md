# Gateway Rollout Gradual

## Flag Principal

Use a variavel de ambiente `AGENT_USE_GATEWAY` para selecionar a superficie de tools exposta ao modelo:

- `AGENT_USE_GATEWAY=true`: modelo usa tools de negocio do gateway.
- `AGENT_USE_GATEWAY=false`: modelo usa tools tecnicas legadas (fluxo atual).

Implementacao em runtime:
- `backend/agents/nodes/response.py`

## Observabilidade e Trilha

Cada chamada do gateway gera log estruturado com:
- tool de negocio chamada
- operacao tecnica mapeada
- usuario e nivel de acesso
- rota (`consulta` ou `execucao`)
- resultado/falha
- latencia (`duration_ms`)

Implementacao:
- `backend/agents/gateway/gateway_service.py`

## Paralelo para Validacao

Durante validacao, rode duas instancias do backend:

1. Instancia A (controle)
- `AGENT_USE_GATEWAY=false`

2. Instancia B (candidate)
- `AGENT_USE_GATEWAY=true`

Estrategia recomendada:
- enviar parte do trafego para cada instancia
- comparar taxa de erro, tempo de resposta e diferencas de resultado
- promover `AGENT_USE_GATEWAY=true` apenas apos estabilidade

## Criterio de Promocao

Promover gateway como padrao quando:
- taxa de erro da instancia B estiver estavel
- sem regressao funcional nos fluxos criticos
- latencia dentro da faixa operacional aceitavel
