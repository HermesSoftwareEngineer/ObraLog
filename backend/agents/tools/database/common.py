from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import unicodedata

from sqlalchemy import desc, func

from backend.db.diario_repository import agrupar_por_data, get_diario_do_dia, get_registros_por_periodo
from backend.db.models import Alert, AlertRead, AlertSeverity, AlertStatus, Clima, LadoPista, NivelAcesso
from backend.db.repository import Repository


def to_dict(obj):
    data = {}
    for key in obj.__table__.columns.keys():
        if key == "senha":
            continue
        value = getattr(obj, key)
        if isinstance(value, Decimal):
            data[key] = float(value)
        elif hasattr(value, "value"):
            data[key] = value.value
        else:
            data[key] = value
    if getattr(obj, "__tablename__", None) == "registros":
        data.setdefault("pista", data.get("lado_pista"))
    return data


def registro_to_dict_with_images(db, registro):
    data = to_dict(registro)
    if db is not None:
        data["imagens_total"] = Repository.registro_imagens.contar_por_registro(db, registro.id)
    else:
        data["imagens_total"] = len(getattr(registro, "_imagens_cache", []))
    return data


def assert_permission(actor_level: str, operation: str, resource: str):
    rules = {
        NivelAcesso.ADMINISTRADOR.value: {
            "usuarios": {"create", "read", "update", "delete"},
            "frentes_servico": {"create", "read", "update", "delete"},
            "registros": {"create", "read", "update", "delete"},
            "alerts": {"create", "read", "update", "delete"},
            "alert_types": {"create", "read", "update", "delete"},
        },
        NivelAcesso.GERENTE.value: {
            "usuarios": {"read"},
            "frentes_servico": {"create", "read", "update", "delete"},
            "registros": {"create", "read", "update", "delete"},
            "alerts": {"create", "read", "update", "delete"},
            "alert_types": {"create", "read", "update", "delete"},
        },
        NivelAcesso.ENCARREGADO.value: {
            "usuarios": {"read"},
            "frentes_servico": {"read"},
            "registros": {"create", "read", "update", "delete"},
            "alerts": {"create", "read", "update"},
            "alert_types": {"read"},
        },
    }

    allowed = rules.get(actor_level, {}).get(resource, set())
    if operation not in allowed:
        raise PermissionError(f"Acesso negado para {operation} em {resource} no nível {actor_level}.")


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.strip().lower().split())


def parse_lado_pista(value: str | None) -> LadoPista | None:
    if not value:
        return None
    normalized = normalize_text(value)
    aliases = {
        "direito": LadoPista.DIREITO,
        "lado direito": LadoPista.DIREITO,
        "direita": LadoPista.DIREITO,
        "lado direita": LadoPista.DIREITO,
        "dir": LadoPista.DIREITO,
        "esquerdo": LadoPista.ESQUERDO,
        "lado esquerdo": LadoPista.ESQUERDO,
        "esquerda": LadoPista.ESQUERDO,
        "lado esquerda": LadoPista.ESQUERDO,
        "esq": LadoPista.ESQUERDO,
    }
    parsed = aliases.get(normalized)
    if parsed is None:
        raise ValueError("lado_pista inválido. Valores aceitos: direito, esquerdo.")
    return parsed


def parse_clima(value: str | None, field_name: str) -> Clima | None:
    if not value:
        return None
    normalized = normalize_text(value)
    aliases = {
        "limpo": Clima.LIMPO,
        "sol": Clima.LIMPO,
        "ensolarado": Clima.LIMPO,
        "nublado": Clima.NUBLADO,
        "chuva": Clima.NUBLADO,
        "chuvoso": Clima.NUBLADO,
        "impraticavel": Clima.IMPRATICAVEL,
        "impraticavel total": Clima.IMPRATICAVEL,
    }
    parsed = aliases.get(normalized)
    if parsed is None:
        raise ValueError(f"{field_name} inválido. Valores aceitos: limpo, nublado, impraticavel.")
    return parsed


def parse_nivel_acesso(value: str | None) -> NivelAcesso | None:
    if not value:
        return None
    normalized = normalize_text(value)
    aliases = {
        "administrador": NivelAcesso.ADMINISTRADOR,
        "admin": NivelAcesso.ADMINISTRADOR,
        "gerente": NivelAcesso.GERENTE,
        "encarregado": NivelAcesso.ENCARREGADO,
    }
    parsed = aliases.get(normalized)
    if parsed is None:
        raise ValueError("nivel_acesso inválido. Valores aceitos: administrador, gerente, encarregado.")
    return parsed


def parse_alert_type(value: str) -> str:
    normalized = normalize_text((value or "").replace("_", " "))
    if not normalized:
        raise ValueError("type é obrigatório.")
    return normalized.replace(" ", "_")


def parse_alert_severity(value: str | None) -> AlertSeverity:
    if not value:
        return AlertSeverity.MEDIA
    normalized = normalize_text(value)
    aliases = {
        "baixa": AlertSeverity.BAIXA,
        "media": AlertSeverity.MEDIA,
        "medio": AlertSeverity.MEDIA,
        "moderada": AlertSeverity.MEDIA,
        "alta": AlertSeverity.ALTA,
        "critica": AlertSeverity.CRITICA,
        "grave": AlertSeverity.CRITICA,
        "urgente": AlertSeverity.CRITICA,
    }
    parsed = aliases.get(normalized)
    if parsed is None:
        raise ValueError("severity inválido. Use: baixa, media, alta, critica.")
    return parsed


def parse_alert_status(value: str) -> AlertStatus:
    normalized = normalize_text(value)
    aliases = {
        "aberto": AlertStatus.ABERTO,
        "em atendimento": AlertStatus.EM_ATENDIMENTO,
        "em_atendimento": AlertStatus.EM_ATENDIMENTO,
        "aguardando peca": AlertStatus.AGUARDANDO_PECA,
        "aguardando_peca": AlertStatus.AGUARDANDO_PECA,
        "resolvido": AlertStatus.RESOLVIDO,
        "cancelado": AlertStatus.CANCELADO,
    }
    parsed = aliases.get(normalized)
    if parsed is None:
        raise ValueError("status inválido. Use: aberto, em_atendimento, aguardando_peca, resolvido, cancelado.")
    return parsed


def default_alert_title(alert_type: str) -> str:
    type_labels = {
        "maquina_quebrada": "Máquina quebrada",
        "acidente": "Acidente",
        "falta_material": "Falta de material",
        "risco_seguranca": "Risco de segurança",
        "outro": "Alerta operacional",
    }
    return type_labels.get(str(alert_type), "Alerta operacional")


def default_alert_description(
    alert_type: str,
    location_detail: str | None = None,
    equipment_name: str | None = None,
) -> str:
    base_by_type = {
        "maquina_quebrada": "Máquina/equipamento com falha operacional",
        "acidente": "Ocorrência de acidente em campo",
        "falta_material": "Ocorrência de falta de material",
        "risco_seguranca": "Ocorrência de risco de segurança",
        "outro": "Ocorrência operacional reportada",
    }
    parts = [base_by_type.get(str(alert_type), "Ocorrência operacional reportada")]
    if location_detail:
        parts.append(f"Local: {location_detail}")
    if equipment_name:
        parts.append(f"Equipamento: {equipment_name}")
    return ". ".join(parts)


def generate_alert_code(db, tenant_id: int | None = None) -> str:
    year = datetime.utcnow().year
    prefix = f"ALT-{year}-"
    query = db.query(func.count(Alert.id)).filter(Alert.code.like(f"{prefix}%"))
    if tenant_id is not None:
        query = query.filter(Alert.tenant_id == tenant_id)
    count = query.scalar() or 0
    return f"{prefix}{count + 1:04d}"


def sync_alert_read_flags(db, alert) -> None:
    latest_read = (
        db.query(AlertRead)
        .filter(AlertRead.alert_id == alert.id)
        .order_by(desc(AlertRead.read_at))
        .first()
    )
    if latest_read:
        alert.is_read = True
        alert.read_at = latest_read.read_at
        alert.read_by = latest_read.worker_id
    else:
        alert.is_read = False
        alert.read_at = None
        alert.read_by = None


def registro_to_diario_item(registro) -> dict:
    data = registro_to_dict_with_images(None, registro)
    data["registrador_nome"] = registro.usuario_registrador.nome if getattr(registro, "usuario_registrador", None) else None
    return data


def build_diario_do_dia_summary(data_alvo: date, registros: list) -> dict:
    registros_out = [registro_to_diario_item(item) for item in registros]
    total_resultado = round(sum(float(item.get("resultado") or 0.0) for item in registros_out), 2)
    dias_impraticaveis = bool(registros) and all(
        (item.get("tempo_manha") == Clima.IMPRATICAVEL.value)
        and (item.get("tempo_tarde") == Clima.IMPRATICAVEL.value)
        for item in registros_out
    )
    manha = sorted({item.get("tempo_manha") for item in registros_out if item.get("tempo_manha")})
    tarde = sorted({item.get("tempo_tarde") for item in registros_out if item.get("tempo_tarde")})
    return {
        "data": data_alvo.isoformat(),
        "registros": registros_out,
        "total_resultado": total_resultado,
        "total_registros": len(registros_out),
        "dias_impraticaveis": dias_impraticaveis,
        "resumo_clima": f"Manhã: {', '.join(manha)} | Tarde: {', '.join(tarde)}",
    }


def resolve_frente_servico_id(
    db,
    frente_servico_id: int | None = None,
    frente_servico_nome: str | None = None,
    tenant_id: int | None = None,
    auto_select_single: bool = False,
) -> int:
    if frente_servico_id is not None:
        try:
            frente = Repository.frentes_servico.obter_por_id(db, frente_servico_id, tenant_id=tenant_id)
        except TypeError:
            frente = Repository.frentes_servico.obter_por_id(db, frente_servico_id)
        if not frente:
            raise ValueError(f"Frente de serviço com ID {frente_servico_id} não encontrada.")
        return frente_servico_id

    try:
        frentes = Repository.frentes_servico.listar(db, tenant_id=tenant_id)
    except TypeError:
        frentes = Repository.frentes_servico.listar(db)
    if not frentes:
        raise ValueError("Nenhuma frente de serviço cadastrada no momento.")

    if not frente_servico_nome:
        if auto_select_single and len(frentes) == 1:
            return frentes[0].id
        opcoes = ", ".join(item.nome for item in frentes[:8] if item.nome)
        raise ValueError(
            "Informe o nome da frente de serviço. "
            f"Opções disponíveis: {opcoes}"
        )

    alvo = normalize_text(frente_servico_nome)
    exatos = [item for item in frentes if normalize_text(item.nome) == alvo]
    if len(exatos) == 1:
        return exatos[0].id

    parciais = [item for item in frentes if alvo in normalize_text(item.nome)]
    candidatos = exatos or parciais
    if len(candidatos) == 1:
        return candidatos[0].id

    if len(candidatos) > 1:
        opcoes = ", ".join(item.nome for item in candidatos[:8] if item.nome)
        raise ValueError(
            "Encontrei mais de uma frente compatível com esse nome. "
            f"Seja mais específico. Opções: {opcoes}"
        )

    opcoes = ", ".join(item.nome for item in frentes[:8] if item.nome)
    raise ValueError(
        f"Não encontrei frente de serviço para '{frente_servico_nome}'. "
        f"Opções disponíveis: {opcoes}"
    )


__all__ = [
    "agrupar_por_data",
    "assert_permission",
    "build_diario_do_dia_summary",
    "default_alert_description",
    "default_alert_title",
    "generate_alert_code",
    "get_diario_do_dia",
    "get_registros_por_periodo",
    "normalize_text",
    "parse_alert_severity",
    "parse_alert_status",
    "parse_alert_type",
    "parse_clima",
    "parse_lado_pista",
    "parse_nivel_acesso",
    "registro_to_dict_with_images",
    "resolve_frente_servico_id",
    "sync_alert_read_flags",
    "to_dict",
]
