"""Supabase Storage helper for PDF and image uploads.

Quando SUPABASE_URL e SUPABASE_SERVICE_KEY não estiverem configurados, os
arquivos são salvos localmente e servidos via endpoints internos.

PRE-REQUISITOS (produção):
  - Criar o bucket "diarios" (privado) para PDFs.
  - Criar o bucket "registros" (privado) para imagens.
  - Definir SUPABASE_URL e SUPABASE_SERVICE_KEY no ambiente.
"""
from __future__ import annotations

import logging
import os
import uuid as _uuid_mod
from pathlib import Path
from typing import Optional

import requests
from requests import Session as _Session

from backend.core.config import settings


def _session() -> _Session:
    """Returns a requests Session for Supabase API calls.

    SSL verification can be disabled via SUPABASE_SSL_VERIFY=false in .env.
    Useful in local dev with Python 3.14+ which enforces stricter X.509 checks
    that reject some intermediate CA certificates in the AWS/Supabase chain.
    Production (Python 3.12 Docker) always verifies correctly.
    """
    s = _Session()
    verify = os.environ.get("SUPABASE_SSL_VERIFY", "true").lower() not in ("false", "0", "no")
    if not verify:
        s.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return s
    try:
        import certifi
        s.verify = certifi.where()
    except ImportError:
        pass
    return s

logger = logging.getLogger("obralog.storage")

# ── PDF (bucket diarios) ─────────────────────────────────────────────────────
_BUCKET = "diarios"
_LOCAL_PREFIX = "local/"
_BACKEND_DIR = Path(__file__).resolve().parent.parent  # ObraLog/backend/
_LOCAL_PDF_DIR = Path(os.environ.get("LOCAL_PDF_DIR", str(_BACKEND_DIR / "uploads" / "diarios")))

# ── Imagens (bucket registros) ───────────────────────────────────────────────
_IMG_BUCKET = "registros"
_LOCAL_IMG_PREFIX = "local-img/"


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
    object_key = f"{tenant_id}/{diario_id}/v{versao}.pdf"

    if not _supabase_configured():
        local_path = _LOCAL_PDF_DIR / str(tenant_id) / diario_id
        local_path.mkdir(parents=True, exist_ok=True)
        file_path = local_path / f"v{versao}.pdf"
        file_path.write_bytes(pdf_bytes)
        logger.info("PDF salvo localmente em %s", file_path)
        return f"{_LOCAL_PREFIX}{tenant_id}/{diario_id}/v{versao}.pdf"

    url = f"{_base_url()}/object/{_BUCKET}/{object_key}"
    resp = _session().put(
        url,
        data=pdf_bytes,
        headers={**_headers(), "Content-Type": "application/pdf"},
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Falha ao fazer upload do PDF: HTTP {resp.status_code} — {resp.text[:200]}"
        )

    return f"{_BUCKET}/{object_key}"


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
        resp = _session().post(
            url,
            json={"expiresIn": expires_in},
            headers={**_headers(), "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            signed = data.get("signedURL") or data.get("signedUrl") or data.get("signed_url")
            if signed:
                if signed.startswith("http"):
                    return signed
                base = (settings.supabase_url or "").rstrip("/")
                # Supabase returns a relative path starting with "/object/sign/..."
                # which must be prefixed with "/storage/v1" to form a valid URL.
                prefix = "" if signed.startswith("/storage/") else "/storage/v1"
                return f"{base}{prefix}{signed}"
    except Exception as exc:
        logger.warning("Falha ao gerar signed URL para %s: %s", storage_path, exc)

    return None


def get_local_pdf_path(storage_path: str) -> Optional[Path]:
    """Resolve a local/ storage_path to an absolute filesystem path."""
    if not storage_path.startswith(_LOCAL_PREFIX):
        return None
    rel = storage_path.removeprefix(_LOCAL_PREFIX)
    return _LOCAL_PDF_DIR / rel


# ---------------------------------------------------------------------------
# Imagens de registro — bucket "registros" (privado)
# ---------------------------------------------------------------------------

def upload_imagem_registro(
    tenant_id: int,
    registro_id: int,
    img_bytes: bytes,
    mime_type: str = "image/jpeg",
    suffix: str = ".jpg",
) -> str:
    """Upload image to Supabase Storage (or local fallback). Returns storage_path.

    storage_path formats:
      Supabase → "registros/{tenant_id}/{registro_id}/{uuid}.ext"
      Local    → "local-img/{uuid}.ext"
    """
    filename = f"{_uuid_mod.uuid4().hex}{suffix}"

    if not _supabase_configured():
        from backend.api.routes.crud.base import UPLOAD_DIR
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        file_path = UPLOAD_DIR / filename
        file_path.write_bytes(img_bytes)
        logger.info("Imagem salva localmente em %s", file_path)
        return f"{_LOCAL_IMG_PREFIX}{filename}"

    # object_key = path WITHIN the bucket (no bucket-name prefix)
    object_key = f"{tenant_id}/{registro_id}/{filename}"
    upload_url = f"{_base_url()}/object/{_IMG_BUCKET}/{object_key}"
    resp = _session().put(
        upload_url,
        data=img_bytes,
        headers={**_headers(), "Content-Type": mime_type},
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Falha ao fazer upload da imagem: HTTP {resp.status_code} — {resp.text[:200]}"
        )
    storage_path = f"{_IMG_BUCKET}/{object_key}"   # "registros/{tenant}/{reg}/{uuid}.ext"
    logger.info("Imagem enviada ao Supabase: %s", storage_path)
    return storage_path


def get_signed_url_imagem(storage_path: str, expires_in: int = 3600) -> Optional[str]:
    """Generate a signed URL for a private Supabase image. Returns None for local images."""
    if not storage_path or storage_path.startswith(_LOCAL_IMG_PREFIX):
        return None  # local images are served directly by the /imagens/{id} endpoint

    if not _supabase_configured():
        return None

    # object_key strips the leading "registros/" bucket prefix (mirrors PDF pattern)
    object_key = storage_path.removeprefix(f"{_IMG_BUCKET}/")
    url = f"{_base_url()}/object/sign/{_IMG_BUCKET}/{object_key}"
    try:
        resp = _session().post(
            url,
            json={"expiresIn": expires_in},
            headers={**_headers(), "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            signed = data.get("signedURL") or data.get("signedUrl") or data.get("signed_url")
            if signed:
                if signed.startswith("http"):
                    return signed
                base = (settings.supabase_url or "").rstrip("/")
                prefix = "" if signed.startswith("/storage/") else "/storage/v1"
                return f"{base}{prefix}{signed}"
        logger.warning("Falha ao gerar signed URL para imagem %s: HTTP %s", storage_path, resp.status_code)
    except Exception as exc:
        logger.warning("Falha ao gerar signed URL para imagem %s: %s", storage_path, exc)
    return None


def download_imagem_registro(storage_path: str) -> Optional[bytes]:
    """Download image bytes from storage (used by PDF/Excel/Word export services).

    Handles all three storage_path formats:
      "registros/..."  → Supabase private bucket (downloaded with service key)
      "local-img/..."  → Local UPLOAD_DIR file
      "/abs/path/..."  → Legacy absolute path stored before migration
    """
    if not storage_path:
        return None

    # Local fallback (new format)
    if storage_path.startswith(_LOCAL_IMG_PREFIX):
        from backend.api.routes.crud.base import UPLOAD_DIR
        p = UPLOAD_DIR / storage_path.removeprefix(_LOCAL_IMG_PREFIX)
        return p.read_bytes() if p.exists() else None

    # Legacy: absolute local path stored before Supabase migration
    p = Path(storage_path)
    if p.is_absolute():
        if p.exists():
            return p.read_bytes()
        # Try resolving relative to UPLOAD_DIR (legacy relative path stored with OS sep)
        from backend.api.routes.crud.base import UPLOAD_DIR
        p2 = UPLOAD_DIR / p.name
        return p2.read_bytes() if p2.exists() else None

    # Supabase private bucket — download with service key
    if not _supabase_configured():
        return None

    object_key = storage_path.removeprefix(f"{_IMG_BUCKET}/")
    url = f"{_base_url()}/object/{_IMG_BUCKET}/{object_key}"
    try:
        resp = _session().get(url, headers=_headers(), timeout=15)
        if resp.status_code == 200:
            return resp.content
        logger.warning("Falha ao baixar imagem %s: HTTP %s", storage_path, resp.status_code)
    except Exception as exc:
        logger.warning("Falha ao baixar imagem %s: %s", storage_path, exc)
    return None
