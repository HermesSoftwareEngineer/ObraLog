from .database import (
    build_alerts_tools,
    build_alert_type_tools,
    build_frentes_servico_tools,
    build_obras_tools,
    build_mensagens_campo_tools,
    build_registros_tools,
    build_usuarios_tools,
)


def get_database_tools(
    actor_user_id: int,
    actor_level: str,
    *,
    tenant_id: int | None = None,
    location_profile: str | None = None,
):
    tools = []
    tools.extend(build_usuarios_tools(actor_user_id=actor_user_id, actor_level=actor_level, tenant_id=tenant_id))
    tools.extend(build_frentes_servico_tools(actor_user_id=actor_user_id, actor_level=actor_level, tenant_id=tenant_id))
    tools.extend(build_obras_tools(actor_user_id=actor_user_id, actor_level=actor_level, tenant_id=tenant_id))
    tools.extend(
        build_registros_tools(
            actor_user_id=actor_user_id,
            actor_level=actor_level,
            tenant_id=tenant_id,
            location_profile=location_profile,
        )
    )
    tools.extend(build_mensagens_campo_tools(actor_user_id=actor_user_id, actor_level=actor_level, tenant_id=tenant_id))
    tools.extend(build_alerts_tools(actor_user_id=actor_user_id, actor_level=actor_level, tenant_id=tenant_id))
    tools.extend(build_alert_type_tools(actor_user_id=actor_user_id, actor_level=actor_level, tenant_id=tenant_id))
    return tools
