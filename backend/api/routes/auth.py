import os
import secrets
import string
from datetime import datetime
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


def _issue_token(user_id: int, email: str) -> str:
    payload = {"sub": user_id, "email": email}
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

        with SessionLocal() as db:
            user = Repository.usuarios.obter_por_id(db, int(user_id))

        if not user:
            return _json_error("Usuário não encontrado.", 401)

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

    if not nome or not email or not senha:
        return _json_error("Campos obrigatórios: nome, email, senha.")

    with SessionLocal() as db:
        if Repository.usuarios.obter_por_email(db, email):
            return _json_error("Email já cadastrado.", 409)

        user = Repository.usuarios.criar(
            db=db,
            nome=nome,
            email=email,
            senha=generate_password_hash(senha),
            nivel_acesso=NivelAcesso.ENCARREGADO,
            telefone=telefone,
            telegram_thread_id=None,
        )

    token = _issue_token(user.id, user.email)
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

    token = _issue_token(user.id, user.email)
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
