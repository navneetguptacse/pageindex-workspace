from __future__ import annotations

import hashlib
import io
import json
import logging
from contextlib import closing
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode, urlsplit
from uuid import UUID

import pypdfium2 as pdfium
from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError
from sqlmodel import Session, func, select, update

from app.config import get_settings
from app.database import SessionDep, lock_auth_transaction
from app.document_storage import (
    legacy_document_path,
    local_document_path,
    pdfium_lock,
    remove_upload,
    upload_path,
)
from app.models import Document, WorkItem, utc_now
from app.pageindex_clients import get_pageindex_client, provider_key, provider_request
from app.preview_cache import page_cache_key, preview_cache
from app.quota import reserve_provider_request
from app.routers.collections import active_collection
from app.schemas import (
    DocumentBatchMove,
    DocumentMove,
    DocumentRead,
    DocumentRename,
    DocumentSelection,
    PagePreviewRead,
)
from app.work_queue import (
    IdempotencyKey,
    commit_work,
    fingerprint,
    new_work,
    prefers_background,
    replay_work,
    requeue_upload,
    retry_upload_status,
)

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def _validate_upload(file: UploadFile, limit: int) -> str:
    if file.size is not None and file.size > limit:
        raise HTTPException(status_code=413, detail="PDF exceeds the upload size limit")
    filename = Path((file.filename or "").replace("\\", "/")).name.strip()
    if not filename or len(filename.encode()) > 200 or "\x00" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    header = file.file.read(5)
    file.file.seek(0)
    if not filename.lower().endswith(".pdf") or header != b"%PDF-":
        raise HTTPException(status_code=415, detail="A PDF file is required")
    return filename


def _upload_documents(
    files: list[UploadFile],
    collection_id: UUID | None,
    metadata: str | None,
    max_total_bytes: int,
    session: Session,
    background: bool = False,
    idempotency_key: str | None = None,
) -> list[Document]:
    try:
        metadata_dict = json.loads(metadata) if metadata is not None else None
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Metadata must be a JSON object"
        ) from exc
    if metadata is not None and not isinstance(metadata_dict, dict):
        raise HTTPException(status_code=400, detail="Metadata must be a JSON object")

    cloud_collection_id = None
    if collection_id is not None:
        collection = active_collection(session, collection_id)
        if collection is None:
            raise HTTPException(status_code=404, detail="Collection not found")
        cloud_collection_id = collection.pageindex_collection_id
        session.rollback()

    limit = get_settings().max_upload_size_mb * 1024**2
    documents = [
        Document(
            doc_id="",
            filename=_validate_upload(file, limit),
            file_size=file.size,
            collection_id=collection_id,
            metadata_=metadata_dict,
        )
        for file in files
    ]
    paths: list[Path] = []
    file_fingerprints: list[tuple[str, str]] = []
    batch_size = 0
    try:
        for file, document in zip(files, documents, strict=True):
            path = upload_path(document)
            path.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with path.open("xb") as output:
                paths.append(path)
                total = 0
                while chunk := file.file.read(1024**2):
                    total += len(chunk)
                    batch_size += len(chunk)
                    if total > limit:
                        raise HTTPException(
                            status_code=413, detail="PDF exceeds the upload size limit"
                        )
                    if batch_size > max_total_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail="Batch exceeds the upload size limit",
                        )
                    output.write(chunk)
                    if background:
                        digest.update(chunk)
                document.file_size = total
            if background:
                file_fingerprints.append((document.filename, digest.hexdigest()))

        if background:
            if collection_id is not None:
                lock_auth_transaction(session)
            work = new_work(
                "upload",
                idempotency_key,
                fingerprint([str(collection_id), metadata_dict, file_fingerprints]),
                [document.id for document in documents],
            )
            previous = replay_work(session, work)
            if previous is None:
                if (
                    collection_id is not None
                    and active_collection(session, collection_id) is None
                ):
                    raise HTTPException(409, "Collection was deleted during upload")
                reserve_provider_request(session, amount=len(documents), commit=False)
                for document in documents:
                    document.doc_id = str(document.id)
                    document.status = "queued"
                session.add_all(documents)
                previous = commit_work(session, work)
                if previous is None:
                    return documents

            for path in paths:
                remove_upload(path)
            return _replayed_uploads(session, previous)

        reserve_provider_request(session, amount=len(documents))
        with provider_request("upload setup"):
            client = get_pageindex_client()
        options = {"collection_id": cloud_collection_id} if cloud_collection_id else {}
        for document, path in zip(documents, paths, strict=True):
            try:
                result = client.submit_document(str(path), **options)
                document.doc_id = result["doc_id"]
                client.wait_document(document.doc_id)
                document.status = "ready"
            except Exception:
                logger.exception("PageIndex upload failed for document %s", document.id)
                document.doc_id = document.doc_id or str(document.id)
                document.status = "failed"
        if collection_id is not None:
            lock_auth_transaction(session)
            if active_collection(session, collection_id) is None:
                raise HTTPException(409, "Collection was deleted during upload")
        session.add_all(documents)
        session.commit()
    except Exception:
        for path in paths:
            remove_upload(path)
        raise
    return documents


def _replayed_uploads(session: Session, work: WorkItem) -> list[Document]:
    documents = []
    for resource_id in work.resource_ids:
        document = session.get(Document, UUID(resource_id))
        if document is None or document.is_deleted:
            raise HTTPException(
                status_code=410, detail="The previous upload has been deleted"
            )
        documents.append(document)
    return documents


def _accept_background(response: Response, prefer: str | None) -> bool:
    if not prefers_background(prefer):
        return False
    response.status_code = 202
    response.headers["Preference-Applied"] = "respond-async"
    return True


@router.post(
    "",
    response_model=DocumentRead,
    status_code=201,
    responses={202: {"description": "Upload queued"}},
    max_body_size=settings.max_upload_size_mb * 1024**2 + 1024**2,
    form_limits={"max_files": 1},
)
def upload_document(
    session: SessionDep,
    response: Response,
    file: Annotated[UploadFile, File()],
    collection_id: UUID | None = None,
    metadata: str | None = None,
    prefer: Annotated[str | None, Header()] = None,
    idempotency_key: IdempotencyKey = None,
) -> Document:
    max_total_bytes = get_settings().max_upload_size_mb * 1024**2
    return _upload_documents(
        [file],
        collection_id,
        metadata,
        max_total_bytes,
        session,
        _accept_background(response, prefer),
        idempotency_key,
    )[0]


@router.post(
    "/batch",
    response_model=list[DocumentRead],
    status_code=201,
    responses={202: {"description": "Upload queued"}},
    max_body_size=settings.max_batch_upload_size_mb * 1024**2 + 1024**2,
    form_limits={"max_files": 10},
)
def upload_documents_batch(
    session: SessionDep,
    response: Response,
    files: Annotated[list[UploadFile], File(min_length=1, max_length=10)],
    collection_id: UUID | None = None,
    metadata: str | None = None,
    prefer: Annotated[str | None, Header()] = None,
    idempotency_key: IdempotencyKey = None,
) -> list[Document]:
    max_total_bytes = get_settings().max_batch_upload_size_mb * 1024**2
    return _upload_documents(
        files,
        collection_id,
        metadata,
        max_total_bytes,
        session,
        _accept_background(response, prefer),
        idempotency_key,
    )


@router.get("", response_model=list[DocumentRead])
def list_documents(
    session: SessionDep, collection_id: UUID | None = None
) -> list[Document]:
    statement = select(Document).where(Document.is_deleted.is_(False))
    if collection_id is not None:
        statement = statement.where(Document.collection_id == collection_id)
    return list(session.exec(statement.order_by(Document.uploaded_at.desc())).all())


def _document_by_provider_id(session: Session, doc_id: str) -> Document | None:
    statement = (
        select(Document)
        .where(Document.doc_id == doc_id)
        .order_by(Document.is_deleted, Document.uploaded_at.desc())
    )
    return session.exec(statement).first()


def _document_by_citation_name(session: Session, identifier: str) -> Document | None:
    filename = identifier.rsplit("/", 1)[-1]
    if not filename.lower().endswith(".pdf"):
        return None

    prefix, _, _ = filename.partition("_")
    try:
        local_id = UUID(prefix)
    except ValueError:
        local_id = None
    if local_id is not None:
        document = session.get(Document, local_id)
        if document is not None and upload_path(document).name == filename:
            return document

    try:
        client = get_pageindex_client()
        provider_id = client.get_document_id(filename)
        if client.get_document(provider_id).get("name") == filename:
            return _document_by_provider_id(session, provider_id)
    except Exception:
        logger.debug("Could not resolve document citation name", exc_info=True)
    return None


def _active_document(session: Session, identifier: str) -> Document:
    document = _document_by_provider_id(session, identifier)
    if document is None:
        try:
            local_id = UUID(identifier)
        except ValueError:
            document = _document_by_citation_name(session, identifier)
        else:
            document = session.get(Document, local_id)
    if document is None or document.is_deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _legacy_path(document: Document) -> Path | None:
    if document.status != "ready":
        return None
    try:
        remote = get_pageindex_client().get_document(document.doc_id)
        return legacy_document_path(document, remote.get("name"))
    except Exception:
        logger.warning("Could not look up the stored name for document %s", document.id)
        return None


def _ensure_page_exists(page: int, total: int) -> None:
    if page > total:
        raise HTTPException(status_code=404, detail="Page not found")


@router.get("/page-preview")
def get_page_preview(
    session: SessionDep,
    doc_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
) -> PagePreviewRead:
    document = _active_document(session, doc_id)
    cache = preview_cache()
    key = page_cache_key(document, page, "preview")
    query = urlencode({"doc_id": doc_id, "page": page})
    image_url = f"/api/v1/documents/page-image?{query}"
    if cache and (payload := cache.get(key)):
        try:
            preview = PagePreviewRead.model_validate_json(payload)
        except ValidationError:
            pass
        else:
            return preview.model_copy(
                update={"filename": document.filename, "image_url": image_url}
            )

    path = local_document_path(document) or _legacy_path(document)
    total_pages = None
    extracted_text = None

    if path:
        try:
            with pdfium_lock, pdfium.PdfDocument(path) as pdf:
                total_pages = len(pdf)
                _ensure_page_exists(page, total_pages)
                with (
                    closing(pdf[page - 1]) as pdf_page,
                    closing(pdf_page.get_textpage()) as text_page,
                ):
                    extracted_text = text_page.get_text_range().strip() or None
        except pdfium.PdfiumError:
            logger.warning("Could not read local PDF for document %s", document.id)

    if extracted_text is None and document.status == "ready":
        try:
            client = get_pageindex_client()
            if total_pages is None:
                total_pages = client.get_document(document.doc_id).get("pageNum")
            content = client.get_page_content(document.doc_id, str(page))
            if content:
                extracted_text = content[0].get("text") or content[0].get("raw_text")
        except Exception:
            logger.warning("Could not retrieve page text for document %s", document.id)

    if total_pages is None:
        raise HTTPException(status_code=404, detail="Page preview not available")
    _ensure_page_exists(page, total_pages)
    preview = PagePreviewRead(
        doc_id=document.doc_id,
        filename=document.filename,
        page=page,
        total_pages=total_pages,
        text=extracted_text,
        image_url=image_url,
    )
    if cache:
        cache.set(key, preview.model_dump_json().encode())
    return preview


@router.get("/page-image", response_class=Response)
def get_page_image(
    session: SessionDep,
    doc_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
) -> Response:
    document = _active_document(session, doc_id)
    cache = preview_cache()
    key = page_cache_key(document, page, "jpeg")
    if cache and (image := cache.get(key)):
        return Response(image, media_type="image/jpeg")

    path = local_document_path(document) or _legacy_path(document)
    if path:
        try:
            with pdfium_lock, pdfium.PdfDocument(path) as pdf:
                _ensure_page_exists(page, len(pdf))
                with closing(pdf[page - 1]) as pdf_page:
                    width, height = pdf_page.get_size()
                    scale = min(2.0, 2400 / max(width, height))
                    with (
                        closing(pdf_page.render(scale=scale)) as bitmap,
                        bitmap.to_pil() as image,
                        io.BytesIO() as output,
                    ):
                        image.save(output, format="JPEG", quality=90)
                        jpeg = output.getvalue()
            if cache:
                cache.set(key, jpeg)
            return Response(jpeg, media_type="image/jpeg")
        except pdfium.PdfiumError:
            logger.warning("Could not render local PDF for document %s", document.id)

    if document.status == "ready":
        try:
            image_url = get_pageindex_client().get_page_image(document.doc_id, page)
            url = urlsplit(image_url)
            if url.scheme in {"http", "https"} and url.netloc:
                return RedirectResponse(image_url)
        except Exception:
            logger.warning("Could not retrieve page image for document %s", document.id)
    raise HTTPException(status_code=404, detail="Page image not found")


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(document_id: UUID, session: SessionDep) -> Document:
    document = session.get(Document, document_id)
    if document is None or document.is_deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.patch("/{document_id}", response_model=DocumentRead)
def rename_document(
    document_id: UUID, body: DocumentRename, session: SessionDep
) -> Document:
    statement = (
        update(Document)
        .where(Document.id == document_id, Document.is_deleted.is_(False))
        .values(
            filename=body.filename,
            original_filename=func.coalesce(
                Document.original_filename, Document.filename
            ),
        )
        .returning(Document)
    )
    document = session.exec(statement).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    session.commit()
    return document


def _move_documents(
    session: Session, document_ids: set[UUID], collection_id: UUID | None
) -> list[Document]:
    lock_auth_transaction(session)
    if collection_id is not None and active_collection(session, collection_id) is None:
        raise HTTPException(404, "Collection not found")
    scope = (Document.id.in_(document_ids), Document.is_deleted.is_(False))
    documents = list(session.exec(select(Document).where(*scope)).all())
    if len(documents) != len(document_ids):
        raise HTTPException(404, "One or more selected PDFs were not found.")
    changing = {doc.id for doc in documents if doc.collection_id != collection_id}
    if changing:
        updated = (
            session.exec(
                update(Document)
                .where(
                    *scope,
                    Document.id.in_(changing),
                    Document.status.in_({"ready", "failed"}),
                )
                .values(collection_id=collection_id)
                .returning(Document.id)
            )
            .scalars()
            .all()
        )
        if len(updated) != len(changing):
            raise HTTPException(
                409, "Wait for processing to finish before moving the selected PDFs."
            )
    session.commit()
    return documents


@router.patch("/batch/collection", response_model=list[DocumentRead])
def move_documents(body: DocumentBatchMove, session: SessionDep) -> list[Document]:
    return _move_documents(session, set(body.document_ids), body.collection_id)


@router.patch("/{document_id}/collection", response_model=DocumentRead)
def move_document(
    document_id: UUID, body: DocumentMove, session: SessionDep
) -> Document:
    return _move_documents(session, {document_id}, body.collection_id)[0]


@router.post("/batch/trash", status_code=204)
def trash_documents(body: DocumentSelection, session: SessionDep) -> None:
    lock_auth_transaction(session)
    document_ids = set(body.document_ids)
    updated = (
        session.exec(
            update(Document)
            .where(Document.id.in_(document_ids), Document.is_deleted.is_(False))
            .values(is_deleted=True, deleted_at=utc_now())
            .returning(Document.id)
        )
        .scalars()
        .all()
    )
    if len(updated) != len(document_ids):
        raise HTTPException(404, "One or more selected PDFs were not found.")
    session.commit()


@router.post("/{document_id}/retry", status_code=202, response_model=DocumentRead)
def retry_document(document_id: UUID, session: SessionDep) -> Document:
    document = get_document(document_id, session)
    if document.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed PDFs can be retried")
    next_status = retry_upload_status(document)
    if next_status != "processing" and local_document_path(document) is None:
        raise HTTPException(
            status_code=409,
            detail="The stored PDF is missing. Upload it again to retry.",
        )
    provider_key()
    updated = session.exec(
        update(Document)
        .where(
            Document.id == document_id,
            Document.is_deleted.is_(False),
            Document.status == "failed",
        )
        .values(status=next_status, processing_error=None)
        .returning(Document.id)
    ).scalar_one_or_none()
    if updated is None:
        raise HTTPException(
            status_code=409,
            detail="This PDF has already changed. Refresh your documents.",
        )
    reserve_provider_request(session, commit=False)
    requeue_upload(session, document)
    session.commit()
    session.refresh(document)
    return document


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: UUID, session: SessionDep) -> None:
    lock_auth_transaction(session)
    document = get_document(document_id, session)
    document.is_deleted = True
    document.deleted_at = utc_now()
    session.commit()
