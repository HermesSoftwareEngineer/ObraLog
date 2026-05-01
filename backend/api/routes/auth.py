import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from backend.db.models import NivelAcesso
from backend.db.repository import Repository
from backend.db.session import SessionLocal


auth_blueprint = Blueprint("auth_v1", __name__, url_prefix="/api/v1/auth")

_TOKEN_MAX_AGE_SECONDS = int(os.environ.get("AUTH_TOKEN_MAX_AGE_SECONDS", "86400"))
_AUTH_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY") or os.environ.get("GOOGLE_API_KEY") or "obralog-dev-secret"
_NON_EXPIRING_LINK_CODE_EXPIRES_AT = datetime(9999, 12, 31, 23, 59, 59)


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=_AUTH_SECRET_KEY, salt="obralog-auth")


def _issue_token(user_id: int, email: str, tenant_id: int) -> str:
    payload = {"sub": user_id, "email": email, "tenant_id": tenant_id}
    return _serializer().dumps(payload)


def _decode_token(token: str) -> dict:
    return _serializer().loads(token, max_age=_TOKEN_MAX_AGE_SECONDS)


def _json_error(message: str, status_code: int = 400):
    return jsonify({"ok": False, "error": message}), status_code


def _user_payload(user) -> dict:
    nivel = user.nivel_acesso.value if hasattr(user.nivel_acesso, "value") else str(user.nivel_acesso)
    return {
        "id": user.id,
        "nome": user.nome,
        "email": user.email,
        "telefone": user.telefone,
        "telegram_chat_id": user.telegram_chat_id,
        "nivel_acesso": nivel,
    }


def _password_matches(stored_password: str, provided_password: str) -> bool:
    if stored_password.startswith(("pbkdf2:", "scrypt:")):
        return check_password_hash(stored_password, provided_password)
    return stored_password == provided_password


def _is_admin(user) -> bool:
    nivel = user.nivel_acesso.value if hasattr(user.nivel_acesso, "value") else str(user.nivel_acesso)
    return nivel == NivelAcesso.ADMINISTRADOR.value


def _is_gerente_or_admin(user) -> bool:
    nivel = user.nivel_acesso.value if hasattr(user.nivel_acesso, "value") else str(user.nivel_acesso)
    return nivel in (NivelAcesso.ADMINISTRADOR.value, NivelAcesso.GERENTE.value)


def _generate_link_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def require_auth(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _json_error("Token ausente ou inválido.", 401)

        token = auth_header.replace("Bearer ", "", 1).strip()
        if not token:
            return _json_error("Token ausente ou inválido.", 401)

        try:
            payload = _decode_token(token)
        except SignatureExpired:
            return _json_error("Token expirado.", 401)
        except BadSignature:
            return _json_error("Token inválido.", 401)

        user_id = payload.get("sub")
        if user_id is None:
            return _json_error("Token inválido.", 401)

        tenant_id = payload.get("tenant_id")
        if tenant_id is not None:
            g.tenant_id = tenant_id

        with SessionLocal() as db:
            user = Repository.usuarios.obter_por_id(db, int(user_id))

        if not user:
            return _json_error("Usuário não encontrado.", 401)

        # Fallback in case token didn't have tenant_id but user exists
        if not hasattr(g, "tenant_id") and hasattr(user, "tenant_id"):
            g.tenant_id = user.tenant_id

        g.current_user = user
        return handler(*args, **kwargs)

    return wrapper


@auth_blueprint.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    nome = data.get("nome")
    email = data.get("email")
    senha = data.get("senha")
    telefone = data.get("telefone")
    invite_code = (data.get("invite_code") or "").strip().upper()

    if not nome or not email or not senha:
        return _json_error("Campos obrigatórios: nome, email, senha.")
    if not invite_code:
        return _json_error("Campos obrigatórios: invite_code.")

    with SessionLocal() as db:
        invite = Repository.user_invite_codes.obter_por_codigo(db, invite_code)
        if not invite:
            return _json_error("Código de convite inválido.", 404)
        if not invite.ativo or invite.usado_em is not None:
            return _json_error("Código de convite já utilizado.", 409)
        now_utc = datetime.now(timezone.utc)
        expira = invite.expira_em
        if expira.tzinfo is None:
            expira = expira.replace(tzinfo=timezone.utc)
        if now_utc > expira:
            return _json_error("Código de convite expirado.", 410)

        tenant_id = invite.tenant_id
        nivel_acesso_str = invite.nivel_acesso or "encarregado"
        nivel_acesso = NivelAcesso(nivel_acesso_str) if nivel_acesso_str in NivelAcesso._value2member_map_ else NivelAcesso.ENCARREGADO

        if Repository.usuarios.obter_por_email(db, email, tenant_id=tenant_id):
            return _json_error("Email já cadastrado nesta unidade.", 409)

        user = Repository.usuarios.criar(
            db=db,
            nome=nome,
            email=email,
            senha=generate_password_hash(senha),
            nivel_acesso=nivel_acesso,
            telefone=telefone,
            telegram_thread_id=None,
            tenant_id=tenant_id,
        )
        Repository.user_invite_codes.marcar_usado(db, invite, usado_por=user.id)

    token = _issue_token(user.id, user.email, user.tenant_id)
    return jsonify({"ok": True, "token": token, "user": _user_payload(user)}), 201


@auth_blueprint.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    senha = data.get("senha")

    if not email or not senha:
        return _json_error("Campos obrigatórios: email, senha.")

    with SessionLocal() as db:
        user = Repository.usuarios.obter_por_email(db, email)
        if not user:
            return _json_error("Credenciais inválidas.", 401)

        if not _password_matches(user.senha or "", senha):
            return _json_error("Credenciais inválidas.", 401)

        # Migração silenciosa de senha em texto plano para hash.
        if user.senha and not user.senha.startswith(("pbkdf2:", "scrypt:")):
            user = Repository.usuarios.atualizar(db, user.id, senha=generate_password_hash(senha))

    token = _issue_token(user.id, user.email, user.tenant_id)
    return jsonify({"ok": True, "token": token, "user": _user_payload(user)})


@auth_blueprint.get("/me")
@require_auth
def me():
    return jsonify({"ok": True, "user": _user_payload(g.current_user)})


@auth_blueprint.patch("/link-telegram")
@require_auth
def link_telegram():
    data = request.get_json(silent=True) or {}
    telegram_chat_id = data.get("telegram_chat_id")
    if not telegram_chat_id:
        return _json_error("Campo obrigatório: telegram_chat_id.")

    with SessionLocal() as db:
        other_user = Repository.usuarios.obter_por_telegram_chat_id(db, str(telegram_chat_id))
        if other_user and other_user.id != g.current_user.id:
            return _json_error("telegram_chat_id já está vinculado a outro usuário.", 409)

        updated = Repository.usuarios.atualizar(
            db,
            g.current_user.id,
            telegram_chat_id=str(telegram_chat_id),
            telegram_thread_id=str(telegram_chat_id),
        )

    return jsonify({"ok": True, "user": _user_payload(updated)})


@auth_blueprint.post("/telegram-link-codes")
@require_auth
def create_telegram_link_code():
    if not _is_admin(g.current_user):
        return _json_error("Apenas administrador pode gerar código de vínculo.", 403)

    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    if user_id is None:
        return _json_error("Campo obrigatório: user_id.")

    with SessionLocal() as db:
        target_user = Repository.usuarios.obter_por_id(db, int(user_id))
        if not target_user:
            return _json_error("Usuário alvo não encontrado.", 404)

        # Gera código único com poucas tentativas.
        code = None
        for _ in range(10):
            candidate = _generate_link_code()
            if not Repository.telegram_link_codes.obter_valido_por_codigo(db, candidate):
                code = candidate
                break

        if not code:
            return _json_error("Não foi possível gerar código único. Tente novamente.", 500)

        link_code = Repository.telegram_link_codes.criar(
            db=db,
            user_id=target_user.id,
            code=code,
            expires_at=_NON_EXPIRING_LINK_CODE_EXPIRES_AT,
            generated_by_user_id=g.current_user.id,
        )

    return jsonify(
        {
            "ok": True,
            "link_code": {
                "code": link_code.code,
                "user_id": link_code.user_id,
                "expires_at": link_code.expires_at.isoformat(),
                "generated_by_user_id": link_code.generated_by_user_id,
            },
        }
    ), 201


# ---------------------------------------------------------------------------
# Invite codes
# ---------------------------------------------------------------------------

_INVITE_EXPIRY_HOURS = 24


def _serialize_invite(invite) -> dict:
    return {
        "id": str(invite.id),
        "codigo": invite.codigo,
        "email_destinatario": invite.email_destinatario,
        "nivel_acesso": invite.nivel_acesso,
        "expira_em": invite.expira_em.isoformat() if invite.expira_em else None,
        "usado_em": invite.usado_em.isoformat() if invite.usado_em else None,
        "ativo": invite.ativo,
        "criado_por": invite.criado_por,
        "created_at": invite.created_at.isoformat() if invite.created_at else None,
    }


@auth_blueprint.post("/invite-codes")
@require_auth
def criar_invite():
    if not _is_gerente_or_admin(g.current_user):
        return _json_error("Permissão negada. Requer perfil Admin ou Gerente.", 403)

    tenant_id = getattr(g, "tenant_id", None)
    if not tenant_id:
        return _json_error("Tenant não identificado no contexto.", 403)

    data = request.get_json(silent=True) or {}
    email_destinatario = data.get("email_destinatario")
    nivel_acesso = data.get("nivel_acesso", "encarregado")
    if nivel_acesso not in NivelAcesso._value2member_map_:
        return _json_error(f"nivel_acesso inválido. Use: {', '.join(NivelAcesso._value2member_map_)}")

    expira_em = datetime.now(timezone.utc) + timedelta(hours=_INVITE_EXPIRY_HOURS)

    with SessionLocal() as db:
        # Gera código único
        codigo = None
        for _ in range(10):
            candidate = _generate_link_code(length=12)
            if not Repository.user_invite_codes.obter_por_codigo(db, candidate):
                codigo = candidate
                break
        if not codigo:
            return _json_error("Não foi possível gerar código único. Tente novamente.", 500)

        invite = Repository.user_invite_codes.criar(
            db=db,
            tenant_id=tenant_id,
            criado_por=g.current_user.id,
            codigo=codigo,
            expira_em=expira_em,
            nivel_acesso=nivel_acesso,
            email_destinatario=email_destinatario,
        )

    return jsonify({"ok": True, "invite": _serialize_invite(invite)}), 201


@auth_blueprint.get("/invite-codes")
@require_auth
def listar_invites():
    if not _is_gerente_or_admin(g.current_user):
        return _json_error("Permissão negada. Requer perfil Admin ou Gerente.", 403)

    tenant_id = getattr(g, "tenant_id", None)
    if not tenant_id:
        return _json_error("Tenant não identificado no contexto.", 403)

    with SessionLocal() as db:
        invites = Repository.user_invite_codes.listar_por_tenant(db, tenant_id, apenas_ativos=True)

    return jsonify({"ok": True, "invites": [_serialize_invite(i) for i in invites]})


@auth_blueprint.delete("/invite-codes/<string:codigo>")
@require_auth
def cancelar_invite(codigo: str):
    if not _is_gerente_or_admin(g.current_user):
        return _json_error("Permissão negada. Requer perfil Admin ou Gerente.", 403)

    tenant_id = getattr(g, "tenant_id", None)
    if not tenant_id:
        return _json_error("Tenant não identificado no contexto.", 403)

    with SessionLocal() as db:
        cancelado = Repository.user_invite_codes.cancelar(db, codigo.upper(), tenant_id)

    if not cancelado:
        return _json_error("Convite não encontrado.", 404)
    return jsonify({"ok": True})
