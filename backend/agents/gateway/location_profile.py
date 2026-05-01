from __future__ import annotations

from dataclasses import dataclass

from backend.db.repository import Repository
from backend.db.session import SessionLocal


@dataclass(frozen=True)
class LocationProfile:
    mode: str
    labels: dict[str, str]
    required_fields: list[str]


def _normalize_mode(value: str | None) -> str:
    raw = (value or "estaca").strip().lower()
    if raw in {"estaca", "km", "text", "texto"}:
        return "texto" if raw == "text" else raw
    return "estaca"


def build_location_profile(location_type: str | None) -> LocationProfile:
    mode = _normalize_mode(location_type)
    if mode == "km":
        return LocationProfile(
            mode="km",
            labels={
                "inicio": "KM inicial",
                "fim": "KM final",
                "descritivo": "Local",
            },
            required_fields=["km_inicial", "km_final"],
        )

    if mode == "texto":
        return LocationProfile(
            mode="texto",
            labels={
                "inicio": "Local inicial",
                "fim": "Local final",
                "descritivo": "Local descritivo",
            },
            required_fields=["local_descritivo"],
        )

    return LocationProfile(
        mode="estaca",
        labels={
            "inicio": "Estaca inicial",
            "fim": "Estaca final",
            "descritivo": "Trecho/estaca textual",
        },
        required_fields=["estaca_inicial", "estaca_final"],
    )


def resolve_runtime_location_context(tenant_id: int | None, obra_id_ativa: int | None = None) -> dict:
    # ObraLog ainda nao possui entidade de obra dedicada; mantemos obra_id_ativa como hint de runtime.
    tenant_location_type = "estaca"
    if tenant_id is not None:
        with SessionLocal() as db:
            tenant = Repository.tenants.obter_por_id(db, int(tenant_id))
            if tenant and getattr(tenant, "location_type", None):
                tenant_location_type = str(tenant.location_type)

    profile = build_location_profile(tenant_location_type)
    return {
        "tenant_id": tenant_id,
        "obra_id_ativa": obra_id_ativa,
        "location_profile": profile.mode,
        "location_labels": profile.labels,
        "location_required_fields": profile.required_fields,
    }
