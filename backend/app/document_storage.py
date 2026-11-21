import logging
from pathlib import Path
from threading import Lock
from uuid import UUID

import pypdfium2 as pdfium

from app.config import get_settings
from app.models import Document

logger = logging.getLogger(__name__)
pdfium_lock = Lock()


def upload_path(document: Document) -> Path:
    filename = Path(
        (document.original_filename or document.filename).replace("\\", "/")
    ).name
    return Path(get_settings().upload_dir) / f"{document.id}_{filename}"


def local_document_path(document: Document) -> Path | None:
    path = upload_path(document)
    return path if not path.is_symlink() and path.is_file() else None


def pdf_page_count(path: Path) -> int | None:
    try:
        with pdfium_lock, pdfium.PdfDocument(path) as pdf:
            return len(pdf)
    except (OSError, pdfium.PdfiumError):
        return None


def legacy_document_path(document: Document, stored_name: object) -> Path | None:
    if not isinstance(stored_name, str):
        return None
    prefix, _, filename = stored_name.partition("_")
    if (
        filename != (document.original_filename or document.filename)
        or Path(stored_name).name != stored_name
    ):
        return None
    try:
        UUID(prefix)
    except ValueError:
        return None
    path = Path(get_settings().upload_dir) / stored_name
    return path if not path.is_symlink() and path.is_file() else None


def remove_upload(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Could not remove upload %s", path.name)
