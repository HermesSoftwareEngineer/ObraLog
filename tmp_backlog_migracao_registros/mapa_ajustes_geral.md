# Mapa Geral de Ajustes - Migracao para Registro Unico com Status

## Objetivo
Consolidar os ajustes necessarios para remover o conceito de rascunho/lancamento e operar apenas com registros, com status e obrigatoriedade condicional para consolidacao.

## 1) Modelo de Dados
### Como esta hoje
- Registro tem varios campos nao nulos em `models.py:165`.
- Existe bloco de lancamentos em `models.py:257`.

### Como deve ficar
- Apenas registro com coluna de status.
- Campos de negocio opcionais no armazenamento.
- Regra condicional para status consolidado.

### Ajustes necessarios
- Adicionar enum de status de registro no modelo e no banco.
- Remover enum e classes de lancamento.
- Tornar campos basicos de registro opcionais no banco.
- Criar validacao condicional: se status = consolidado, campos basicos atuais devem existir.

### Pontos SQL atuais para alterar
- `schema.sql:51`
- `20260414_010_ingestao_lancamentos_e_integridade_registros.up.sql:24`
- `session.py:209`

## 2) Repositorio
### Como esta hoje
- Criacao de registro exige assinatura com campos obrigatorios em `repository.py:182`.
- Existe repositorio de lancamentos em `repository.py:380` (aprox.).

### Como deve ficar
- Criacao e atualizacao parcial de registro.
- Transicao explicita de status com regra de consolidacao.

### Ajustes necessarios
- Flexibilizar assinatura de criacao/atualizacao para aceitar parciais.
- Adicionar metodo de transicao de status com validacao de regra para consolidado.
- Remover classes de repositorio de lancamento.

## 3) API REST
### Como esta hoje
- Criacao de registro exige obrigatorios em `registros.py:27`.
- Existe API de lancamentos em `operacional.py:73`.

### Como deve ficar
- Somente API de registro com status.

### Ajustes necessarios
- Remover ou desativar endpoints de lancamentos.
- Criar endpoint para transicao de status de registro.
- Permitir POST de registro parcial.
- Aplicar regra: so consolidado exige dados basicos preenchidos.
- Manter mensagens-campo e auditoria.

## 4) Agente e Gateway
### Como esta hoje
- Prompt prioriza rascunho em `prompts.py:8`.
- Tools de rascunho no gateway em `gateway_tools.py:463`.
- Tools de lancamento carregadas em `__init__.py:3` e `database_tools.py:4`.

### Como deve ficar
- Agente opera somente registros e status de registro.

### Ajustes necessarios
- Remover `build_lancamentos_tools` do carregamento.
- Remover tools de criar/atualizar/confirmar lancamento.
- Incluir tool para mudar status do registro.
- Ajustar sugestao de campos faltantes para tipo registro, removendo `lancamento_operacional` em `rag_service.py:108`.
- Atualizar intents permitidas em `policies.py:31`.

## 5) Mappers e Testes
### Como esta hoje
- Mappers e testes focados em lancamentos em `mappers.py:295` e `test_business_output.py:107`.

### Como deve ficar
- Mappers e testes focados em registros com status.

### Ajustes necessarios
- Substituir `map_consultar_lancamentos_operacionais_output` por consulta de registros operacionais, se essa leitura ainda for exposta.
- Reescrever testes de gateway para o novo fluxo.

## 6) Documentacao
### Como esta hoje
- Varias docs descrevem ciclo de rascunho e lancamentos, como `DB_DESENHO_TECNICO_20260414.md:45` e `20260414_api_frontend_lancamentos_mensagens.md:1`.

### Como deve ficar
- Documentacao sem mencao a rascunho/lancamento.

### Ajustes necessarios
- Revisar docs tecnicas e de contrato de API.
- Atualizar status de endpoints em `STATUS_ENDPOINTS.md:69`.

## Regras de Negocio Alvo (Resumo)
- Registros podem nascer incompletos (sem campos obrigatorios no momento da criacao).
- O status governa exigencias de consistencia.
- Apenas status `consolidado` exige preenchimento completo dos campos basicos atuais.
- Fluxo operacional e de API nao deve mencionar rascunho/lancamento.
