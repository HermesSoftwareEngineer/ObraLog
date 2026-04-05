from backend.agents.instructions_store import read_agent_instructions


SYSTEM_PROMPT_BASE = (
    "Você é o assistente de diário de obra. "
    "Responda somente em pt-BR, em texto simples para Telegram e sem markdown. "
    "Se faltar informação obrigatória, faça perguntas curtas e objetivas. "
    "Antes de salvar qualquer dado, confirme explicitamente com o usuário. "
    "Após escrita, informe claramente o que foi registrado ou alterado."
)


def build_system_prompt() -> str:
    instructions = read_agent_instructions().strip()
    if not instructions:
        return SYSTEM_PROMPT_BASE

    return (
        f"{SYSTEM_PROMPT_BASE}\n\n"
        "Instruções operacionais editáveis:\n"
        f"{instructions}"
    )
