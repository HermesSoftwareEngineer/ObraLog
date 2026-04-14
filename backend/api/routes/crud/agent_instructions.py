from backend.api.routes.auth import require_auth
from backend.agents.instructions_store import get_instructions_path, read_agent_instructions, write_agent_instructions

from .base import api_blueprint, _is_admin, _json_error, _to_project_relative


@api_blueprint.route("/agent/instructions", methods=["GET"])
@require_auth
def obter_instrucoes_agente():
    from flask import g

    if not _is_admin(g.current_user):
        return _json_error("Apenas administradores podem visualizar as instrucoes do agente.", 403)

    path = get_instructions_path()
    content = read_agent_instructions()
    return {
        "ok": True,
        "path": _to_project_relative(path),
        "content": content,
        "exists": path.exists(),
    }


@api_blueprint.route("/agent/instructions", methods=["PUT", "PATCH"])
@require_auth
def atualizar_instrucoes_agente():
    from flask import g, request

    if not _is_admin(g.current_user):
        return _json_error("Apenas administradores podem editar as instrucoes do agente.", 403)

    data = request.get_json(silent=True) or {}
    content = data.get("content")

    if not isinstance(content, str):
        return _json_error("Campo obrigatorio ausente: content")

    saved_path = write_agent_instructions(content)
    return {
        "ok": True,
        "path": _to_project_relative(saved_path),
        "content": content,
    }
