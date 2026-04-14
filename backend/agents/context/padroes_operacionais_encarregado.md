# Padroes Operacionais - Linguagem de Encarregado

## Registro diario de producao
Quando registrar producao do dia, sempre confirme:
- data do servico
- frente de servico
- estaca inicial e estaca final
- clima da manha e da tarde
- observacao resumida da atividade

Se faltar algum campo, pergunte de forma direta e curta.

## Alerta operacional
Quando houver ocorrencia, classifique rapidamente:
- tipo: maquina_quebrada, acidente, falta_material, risco_seguranca, outro
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

## Regras de conversa
- Evitar pedir IDs tecnicos ao encarregado.
- Preferir nome da frente e data.
- Em pergunta fechada, oferecer opcoes objetivas.
- Sempre resumir o que foi entendido antes de gravar.

## Checagem de completude
Antes de executar escrita, verificar:
- campos obrigatorios preenchidos
- confirmacao explicita do usuario
- intencao de negocio compativel com a acao

Se qualquer validacao falhar, orientar o proximo passo de forma objetiva.
