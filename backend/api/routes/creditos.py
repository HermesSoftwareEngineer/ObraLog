from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, request

from backend.api.routes.auth import require_auth
from backend.db.models import NivelAcesso
from backend.db.session import SessionLocal
from backend.services.credito_service import (
    adicionar_creditos_avulsos,
    consultar_saldo,
)

creditos_v1 = Blueprint("creditos_v1", __name__, url_prefix="/api/v1/creditos")


def _json_error(message: str, status_code: int = 400):
    return jsonify({"ok": False, "error": message}), status_code


def _is_admin(user) -> bool:
    nivel = user.nivel_acesso.value if hasattr(user.nivel_acesso, "value") else str(user.nivel_acesso)
    return nivel == NivelAcesso.ADMINISTRADOR.value


def _is_gerente_or_admin(user) -> bool:
    nivel = user.nivel_acesso.value if hasattr(user.nivel_acesso, "value") else str(user.nivel_acesso)
    return nivel in (NivelAcesso.ADMINISTRADOR.value, NivelAcesso.GERENTE.value)


@creditos_v1.get("/saldo")
@require_auth
def saldo():
    with SessionLocal() as db:
        saldo_info = consultar_saldo(db, g.tenant_id)
    return jsonify({"ok": True, **saldo_info})


@creditos_v1.get("/historico")
@require_auth
def historico():
    if not _is_gerente_or_admin(g.current_user):
        return _json_error("Acesso restrito a gerentes e administradores.", 403)

    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(max(1, int(request.args.get("per_page", 20))), 100)
    except (TypeError, ValueError):
        return _json_error("Parâmetros de paginação inválidos.")

    with SessionLocal() as db:
        from backend.db.models import CreditoTransacao

        q = (
            db.query(CreditoTransacao)
            .filter(CreditoTransacao.tenant_id == g.tenant_id)
            .order_by(CreditoTransacao.criada_em.desc())
        )
        total = q.count()
        items = q.offset((page - 1) * per_page).limit(per_page).all()

        return jsonify({
            "ok": True,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page if per_page else 1,
            "items": [
                {
                    "id": str(t.id),
                    "operacao": t.operacao,
                    "creditos": t.creditos,
                    "descricao": t.descricao,
                    "referencia_id": t.referencia_id,
                    "criada_em": t.criada_em.isoformat() if t.criada_em else None,
                }
                for t in items
            ],
        })


@creditos_v1.post("/recarregar")
@require_auth
def recarregar():
    if not _is_admin(g.current_user):
        return _json_error("Acesso restrito a administradores.", 403)

    body = request.get_json() or {}
    quantidade = body.get("quantidade")
    descricao = body.get("descricao")

    if not isinstance(quantidade, int) or quantidade <= 0:
        return _json_error("quantidade deve ser um inteiro positivo.")

    with SessionLocal() as db:
        try:
            adicionar_creditos_avulsos(db, g.tenant_id, quantidade, descricao)
        except ValueError as exc:
            return _json_error(str(exc), 404)

    return jsonify({"ok": True, "message": f"{quantidade} crédito(s) adicionado(s)."})


@creditos_v1.post("/atribuir-plano")
@require_auth
def atribuir_plano():
    if not _is_admin(g.current_user):
        return _json_error("Acesso restrito a administradores.", 403)

    body = request.get_json() or {}
    plano_nome = body.get("plano_nome")

    if not plano_nome:
        return _json_error("plano_nome é obrigatório.")

    with SessionLocal() as db:
        from backend.db.models import Plano, TenantAssinatura

        plano = (
            db.query(Plano)
            .filter(Plano.nome == plano_nome, Plano.ativo.is_(True))
            .first()
        )
        if not plano:
            return _json_error(f"Plano '{plano_nome}' não encontrado.", 404)

        assinatura = (
            db.query(TenantAssinatura)
            .filter(TenantAssinatura.tenant_id == g.tenant_id)
            .first()
        )

        if assinatura is None:
            assinatura = TenantAssinatura(
                tenant_id=g.tenant_id,
                plano_id=plano.id,
                status="ativa",
                creditos_plano=plano.creditos_mensais,
                creditos_avulsos=0,
                proximo_reset_em=datetime.now(timezone.utc) + timedelta(days=30),
            )
            db.add(assinatura)
            msg = "Plano atribuído com sucesso."
        else:
            assinatura.plano_id = plano.id
            msg = "Plano atualizado com sucesso."

        db.commit()

    return jsonify({"ok": True, "message": msg, "plano": plano_nome})


@creditos_v1.get("/planos")
@require_auth
def listar_planos():
    with SessionLocal() as db:
        from backend.db.models import Plano

        planos = (
            db.query(Plano)
            .filter(Plano.ativo.is_(True))
            .order_by(Plano.creditos_mensais)
            .all()
        )
        return jsonify({
            "ok": True,
            "items": [
                {
                    "id": p.id,
                    "nome": p.nome,
                    "creditos_mensais": p.creditos_mensais,
                    "preco_mensal": float(p.preco_mensal) if p.preco_mensal is not None else None,
                    "custo_credito_avulso": float(p.custo_credito_avulso) if p.custo_credito_avulso is not None else None,
                }
                for p in planos
            ],
        })
