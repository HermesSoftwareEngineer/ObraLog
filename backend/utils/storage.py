"""Supabase Storage helper for PDF uploads.

Quando SUPABASE_URL e SUPABASE_SERVICE_KEY não estiverem configurados, os PDFs
são salvos localmente em LOCAL_PDF_DIR (padrão: backend/uploads/diarios) e
servidos via endpoint interno /api/v1/diarios-files/<path>.

PRE-REQUISITO (produção): criar o bucket 'diarios' no painel do Supabase e
definir SUPABASE_URL e SUPABASE_SERVICE_KEY no ambiente.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import requests

from backend.core.config import settings

logger = logging.getLogger("obralog.storage")

_BUCKET = "diarios"
_LOCAL_PREFIX = "local/"
_BACKEND_DIR = Path(__file__).resolve().parent.parent  # ObraLog/backend/
_LOCAL_PDF_DIR = Path(os.environ.get("LOCAL_PDF_DIR", str(_BACKEND_DIR / "uploads" / "diarios")))


def _supabase_configured() -> bool:
    return bool(settings.supabase_url and settings.supabase_service_key)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "apikey": settings.supabase_service_key or "",
    }


def _base_url() -> str:
    url = (settings.supabase_url or "").rstrip("/")
    return f"{url}/storage/v1"


def upload_pdf_diario(
    tenant_id: int,
    diario_id: str,
    versao: int,
    pdf_bytes: bytes,
) -> str:
    """Upload PDF to Supabase Storage (or local fallback). Returns the storage_path."""
    path = f"diarios/{tenant_id}/{diario_id}/v{versao}.pdf"

    if not _supabase_configured():
        local_path = _LOCAL_PDF_DIR / str(tenant_id) / diario_id
        local_path.mkdir(parents=True, exist_ok=True)
        file_path = local_path / f"v{versao}.pdf"
        file_path.write_bytes(pdf_bytes)
        logger.info("PDF salvo localmente em %s", file_path)
        return f"{_LOCAL_PREFIX}{tenant_id}/{diario_id}/v{versao}.pdf"

    url = f"{_base_url()}/object/{_BUCKET}/{path}"
    resp = requests.put(
        url,
        data=pdf_bytes,
        headers={**_headers(), "Content-Type": "application/pdf"},
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Falha ao fazer upload do PDF: HTTP {resp.status_code} — {resp.text[:200]}"
        )

    return path


def get_signed_url_diario(storage_path: str, expires_in: int = 3600) -> Optional[str]:
    """Return a URL for the PDF. Uses local server URL when Supabase is not configured."""
    if storage_path.startswith(_LOCAL_PREFIX):
        rel = storage_path.removeprefix(_LOCAL_PREFIX)
        api_base = os.environ.get("API_BASE_URL", "http://localhost:5000")
        return f"{api_base}/api/v1/diarios-files/{rel}"

    if not _supabase_configured():
        logger.warning("Supabase Storage não configurado; signed URL indisponível.")
        return None

    bucket_path = storage_path.removeprefix("diarios/")
    url = f"{_base_url()}/object/sign/{_BUCKET}/{bucket_path}"

    try:
        resp = requests.post(
            url,
            json={"expiresIn": expires_in},
            headers={**_headers(), "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            signed = data.get("signedURL") or data.get("signedUrl") or data.get("signed_url")
            if signed:
                base = (settings.supabase_url or "").rstrip("/")
                if signed.startswith("http"):
                    return signed
                return f"{base}{signed}"
    except Exception as exc:
        logger.warning("Falha ao gerar signed URL para %s: %s", storage_path, exc)

    return None


def get_local_pdf_path(storage_path: str) -> Optional[Path]:
    """Resolve a local/ storage_path to an absolute filesystem path."""
    if not storage_path.startswith(_LOCAL_PREFIX):
        return None
    rel = storage_path.removeprefix(_LOCAL_PREFIX)
    return _LOCAL_PDF_DIR / rel
