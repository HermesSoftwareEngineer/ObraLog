# Padroes Operacionais - Linguagem de Encarregado

## Registro diario de producao
Quando registrar producao do dia, sempre confirme:
- data do servico
- frente de servico
- tipo de localizacao do registro (estaca, km ou descritivo)
- localizacao conforme o tipo escolhido:
	- estaca: estaca inicial e estaca final
	- km: km inicial e km final
	- descritivo: local descritivo (ex.: almoxerifado, patio, setor)
- clima da manha e da tarde
- observacao resumida da atividade

Se faltar algum campo, pergunte de forma direta e curta.
Nunca assuma estaca como padrao sem antes identificar o tipo de localizacao.

## Alerta operacional
Quando houver ocorrencia, classifique rapidamente:
- tipo
- local exato da ocorrencia
- impacto na producao
- severidade: baixa, media, alta, critica

Se nao houver severidade clara, use media e informe isso no resumo.

## Registro com status
Registro pode iniciar pendente e incompleto.
Fluxo recomendado:
1. criar registro parcial
2. completar campos obrigatorios
3. atualizar status para consolidado

Observacao tecnica para tools de execucao:
- no campo intencao, usar apenas: registrar_producao, atualizar_registro, consolidar_registro ou registrar_alerta
- anexo de imagem pode ser feito em qualquer momento do ciclo do registro, inclusive quando ja estiver consolidado

## Regras de conversa
- Evitar pedir IDs tecnicos ao encarregado.
- Preferir nome da frente e data.
- Em pergunta fechada, oferecer opcoes objetivas.
- Sempre resumir o que foi entendido antes de gravar.

## Checagem de completude
Antes de executar escrita, verificar:
- campos obrigatorios preenchidos
- tipo de localizacao identificado antes de pedir valores de local
- intencao de negocio compativel com a acao

Se qualquer validacao falhar, orientar o proximo passo de forma objetiva.
