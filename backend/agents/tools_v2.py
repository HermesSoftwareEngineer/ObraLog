import json

def registrar_clima(data: str, frente_servico_id: int, condicao: str, periodo: str = "manha"):
    """
    Registra ou atualiza a condição climática de um dia de obra.
    Útil quando o encarregado manda "Dia chuvoso", "Chuva constante".
    """
    # TODO: Invocar backend/DB para atualizar o Diario
    print(f"Clima registrado: {condicao} no periodo {periodo} para o dia {data}")
    return json.dumps({"status": "sucesso", "clima": condicao})


def registrar_atividade(data: str, frente_servico_id: int, descricao: str, estaca_inicial: str = None, estaca_final: str = None, equipamentos: list = None):
    """
    Registra uma atividade pontual ocorrida durante o dia.
    Ex: "Limpeza manual", "Montagem de forma e concretagem", etc.
    """
    # TODO: Invocar backend/DB para inserir a Atividade
    print(f"Atividade registrada: {descricao} nas estacas {estaca_inicial}-{estaca_final}")
    return json.dumps({"status": "sucesso", "atividade": descricao})


def registrar_producao(atividade_id: int, quantidade: float, unidade_medida: str):
    """
    Associa dados de produção/medicao a uma atividade existente.
    Ex: 38 (quantidade) peças (unidade_medida).
    """
    # TODO: Invocar backend/DB para inserir Producao
    print(f"Producao vinculada: {quantidade} {unidade_medida}")
    return json.dumps({"status": "sucesso", "producao": quantidade})


# Lista de tools que serão injetadas no Agente / LangChain / OpenAI
TOOLS_DIARIO_OBRA = [
    registrar_clima,
    registrar_atividade,
    registrar_producao
]
