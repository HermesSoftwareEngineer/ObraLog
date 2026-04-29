from .database import (
    build_alerts_tools,
    build_alert_type_tools,
    build_frentes_servico_tools,
    build_mensagens_campo_tools,
    build_registros_tools,
    build_usuarios_tools,
)


def get_database_tools(actor_user_id: int, actor_level: str):
    tools = []
    tools.extend(build_usuarios_tools(actor_user_id=actor_user_id, actor_level=actor_level))
    tools.extend(build_frentes_servico_tools(actor_user_id=actor_user_id, actor_level=actor_level))
    tools.extend(build_registros_tools(actor_user_id=actor_user_id, actor_level=actor_level))
    tools.extend(build_mensagens_campo_tools(actor_user_id=actor_user_id, actor_level=actor_level))
    tools.extend(build_alerts_tools(actor_user_id=actor_user_id, actor_level=actor_level))
    tools.extend(build_alert_type_tools(actor_user_id=actor_user_id, actor_level=actor_level))
    return tools
