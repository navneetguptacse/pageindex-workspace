import logging
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select, update

from app.database import SessionDep, lock_auth_transaction
from app.document_storage import (
    legacy_document_path,
    local_document_path,
    remove_upload,
)
from app.models import ChatSession, Collection, Document, ExtractJob
from app.pageindex_clients import get_pageindex_client, provider_request
from app.schemas import TrashBatchRequest, TrashItemRead, TrashItemRef

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/trash", tags=["trash"])

TrashRecord = Collection | Document | ChatSession | ExtractJob
TRASH_MODELS = {
    "collection": Collection,
    "document": Document,
    "chat": ChatSession,
    "extract": ExtractJob,
}


def _find_trash_record(session: Session, item: TrashItemRef) -> TrashRecord | None:
    model = TRASH_MODELS[item.type]
    try:
        key = item.id if model is ChatSession else UUID(item.id)
    except ValueError:
        return None
    record = session.get(model, key)
    return record if record is not None and record.deleted_at is not None else None


def _trash_records(session: Session) -> Iterable[TrashRecord]:
    for model in TRASH_MODELS.values():
        yield from session.exec(select(model).where(model.deleted_at.is_not(None)))


@router.get("/items")
def list_trash_items(session: SessionDep) -> list[TrashItemRead]:
    items = []
    names = dict(session.exec(select(Collection.id, Collection.name)).all())
    for record in _trash_records(session):
        collection_id = None
        details = None
        if isinstance(record, Collection):
            kind, title = "collection", record.name
        elif isinstance(record, Document):
            kind, title = "document", record.filename
            details = f"Document ID: {record.doc_id}"
            collection_id = record.collection_id
        elif isinstance(record, ChatSession):
            kind, title = "chat", record.title or "Untitled Conversation"
            details = f"Document: {record.doc_id}" if record.doc_id else "All Documents"
        else:
            kind, title = "extract", record.schema_name or "Extraction Job"
            details = f"Status: {record.status}"
        items.append(
            TrashItemRead(
                id=str(record.id),
                type=kind,
                title=title,
                details=details,
                deleted_at=record.deleted_at,
                collection_id=collection_id,
                collection_name=names.get(collection_id),
            )
        )
    return sorted(items, key=lambda item: item.deleted_at, reverse=True)


def _collections_first(items: Iterable[TrashItemRef]) -> list[TrashItemRef]:
    return sorted(items, key=lambda item: item.type != "collection")


@router.post("/restore")
def restore_trash_items(session: SessionDep, body: TrashBatchRequest) -> dict[str, int]:
    lock_auth_transaction(session)
    count = 0
    for item in _collections_first(body.items):
        record = _find_trash_record(session, item)
        if record is None:
            continue
        record.deleted_at = None
        count += 1
        if isinstance(record, Collection):
            restored = session.exec(
                update(Document)
                .where(
                    Document.collection_id == record.id,
                    Document.is_deleted.is_(True),
                    Document.trashed_with_collection.is_(True),
                )
                .values(
                    is_deleted=False, deleted_at=None, trashed_with_collection=False
                )
            )
            count += restored.rowcount
        else:
            record.is_deleted = False
            if isinstance(record, Document):
                record.trashed_with_collection = False
                if (
                    record.collection is not None
                    and record.collection.deleted_at is not None
                ):
                    record.collection.deleted_at = None
                    count += 1
    session.commit()
    return {"restored": count}


def _purge_document(session: Session, document: Document) -> Path | None:
    path = local_document_path(document)
    other_reference = session.exec(
        select(Document.id).where(
            Document.doc_id == document.doc_id, Document.id != document.id
        )
    ).first()
    if other_reference is not None or document.doc_id == str(document.id):
        return path
    with provider_request("document deletion"):
        client = get_pageindex_client()
    if path is None:
        try:
            stored_name = client.get_document(document.doc_id).get("name")
            path = legacy_document_path(document, stored_name)
        except Exception:
            logger.warning(
                "Could not look up the stored name for document %s", document.id
            )
    with provider_request("document deletion", missing_ok=True):
        client.delete_document(document.doc_id)
    return path


def _purge_records(session: Session, items: Iterable[TrashItemRef]) -> int:
    count = 0
    for item in _collections_first(items):
        lock_auth_transaction(session)
        record = _find_trash_record(session, item)
        if record is None:
            session.rollback()
            continue
        group: list[TrashRecord] = []
        if isinstance(record, Collection):
            if any(not pdf.is_deleted for pdf in record.documents):
                raise HTTPException(409, "This collection contains an active PDF.")
            group.extend(record.documents)
        group.append(record)
        paths = []
        error = None
        for member in group:
            if isinstance(member, Document):
                try:
                    if path := _purge_document(session, member):
                        paths.append(path)
                except HTTPException as exc:
                    error = exc
                    break
            session.delete(member)
            count += 1
        session.commit()
        for path in paths:
            remove_upload(path)
        if error is not None:
            raise error
    return count


@router.post("/permanent-delete")
def permanent_delete_items(
    session: SessionDep, body: TrashBatchRequest
) -> dict[str, int]:
    return {"deleted": _purge_records(session, body.items)}


@router.delete("/empty")
def empty_trash(session: SessionDep) -> dict[str, int]:
    items = [
        TrashItemRef(id=str(row_id), type=kind)
        for kind, model in TRASH_MODELS.items()
        for row_id in session.exec(
            select(model.id).where(model.deleted_at.is_not(None))
        )
    ]
    session.rollback()
    return {"purged": _purge_records(session, items)}
