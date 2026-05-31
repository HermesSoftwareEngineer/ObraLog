"""
Migra imagens de registro do armazenamento local para o Supabase Storage.

Percorre todas as entradas de registro_imagens que tenham storage_path local
(absoluto ou com prefixo "local-img/") e sem caminho Supabase, faz upload
para o bucket "registros" e atualiza o registro no banco.

Uso:
    cd ObraLog/
    python scripts/migrate_images_to_supabase.py [--dry-run]

Pré-requisitos:
    - SUPABASE_URL e SUPABASE_SERVICE_KEY configurados no .env
    - Bucket "registros" criado no Supabase (privado)
    - Backend com as novas funções de storage.py deployado
"""
from __future__ import annotations

import sys
import argparse
import logging
from pathlib import Path

# Garante que o root do projeto está no path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from backend.db.session import SessionLocal
from backend.db.models import RegistroImagem
from backend.api.routes.crud.base import UPLOAD_DIR
from backend.utils.storage import (
    upload_imagem_registro,
    _supabase_configured,
    _LOCAL_IMG_PREFIX,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("migrate_images")


def _resolve_local_file(storage_path: str) -> Path | None:
    """Resolve um storage_path local para Path absoluto, ou None se não encontrado."""
    if not storage_path:
        return None

    if storage_path.startswith(_LOCAL_IMG_PREFIX):
        p = UPLOAD_DIR / storage_path.removeprefix(_LOCAL_IMG_PREFIX)
        return p if p.exists() else None

    p = Path(storage_path)
    if p.is_absolute():
        if p.exists():
            return p
        # Tenta só pelo nome no UPLOAD_DIR (legacy path com outro prefix)
        p2 = UPLOAD_DIR / p.name
        return p2 if p2.exists() else None

    # Caminho relativo sem prefixo reconhecido
    p2 = UPLOAD_DIR / Path(storage_path).name
    return p2 if p2.exists() else None


def _is_supabase_path(storage_path: str) -> bool:
    return storage_path.startswith("registros/")


def run(dry_run: bool = False) -> None:
    if not _supabase_configured():
        logger.error("SUPABASE_URL e/ou SUPABASE_SERVICE_KEY não configurados. Abortando.")
        sys.exit(1)

    logger.info("Iniciando migração%s...", " (DRY RUN)" if dry_run else "")

    migrated = 0
    skipped = 0
    failed = 0
    not_found = 0

    with SessionLocal() as db:
        imagens = (
            db.query(RegistroImagem)
            .filter(RegistroImagem.storage_path.isnot(None))
            .order_by(RegistroImagem.id.asc())
            .all()
        )

        logger.info("Total de imagens com storage_path: %d", len(imagens))

        for img in imagens:
            storage_path = img.storage_path or ""

            if _is_supabase_path(storage_path):
                logger.debug("Imagem %d já está no Supabase (%s). Pulando.", img.id, storage_path)
                skipped += 1
                continue

            local_file = _resolve_local_file(storage_path)
            if local_file is None:
                logger.warning(
                    "Imagem %d: arquivo local não encontrado (storage_path=%r). Pulando.",
                    img.id, storage_path,
                )
                not_found += 1
                continue

            mime_type = img.mime_type or "image/jpeg"
            suffix = local_file.suffix or ".jpg"

            if dry_run:
                logger.info(
                    "[DRY RUN] Imagem %d: %s → Supabase registros/%s/%s/...",
                    img.id, local_file.name, img.tenant_id, img.registro_id,
                )
                migrated += 1
                continue

            try:
                img_bytes = local_file.read_bytes()
                new_storage_path = upload_imagem_registro(
                    tenant_id=img.tenant_id,
                    registro_id=img.registro_id,
                    img_bytes=img_bytes,
                    mime_type=mime_type,
                    suffix=suffix,
                )
                img.storage_path = new_storage_path
                db.flush()
                logger.info(
                    "Imagem %d migrada: %s → %s",
                    img.id, local_file.name, new_storage_path,
                )
                migrated += 1
            except Exception as exc:
                logger.error("Imagem %d: falha ao migrar — %s", img.id, exc)
                failed += 1

        if not dry_run:
            db.commit()
            logger.info("Commit realizado.")

    logger.info(
        "Concluído. migradas=%d | já no Supabase=%d | arquivo não encontrado=%d | falhas=%d",
        migrated, skipped, not_found, failed,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migra imagens locais para Supabase Storage.")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem fazer upload nem alterar o banco.")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
