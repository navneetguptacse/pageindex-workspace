import logging
from collections.abc import Iterable
from uuid import UUID

from fastapi import APIRouter
from sqlmodel import Session, select

from app.database import SessionDep
from app.document_storage import (
    legacy_document_path,
    local_document_path,
    remove_upload,
)
from app.models import ChatSession, Document, ExtractJob
from app.pageindex_clients import get_pageindex_client, provider_request
from app.schemas import TrashBatchRequest, TrashItemRead, TrashItemRef

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/trash", tags=["trash"])

TrashRecord = Document | ChatSession | ExtractJob
TRASH_MODELS = {"document": Document, "chat": ChatSession, "extract": ExtractJob}


def _find_trash_record(session: Session, item: TrashItemRef) -> TrashRecord | None:
    model = TRASH_MODELS[item.type]
    try:
        key = item.id if model is ChatSession else UUID(item.id)
    except ValueError:
        return None
    record = session.get(model, key)
    return record if record and record.is_deleted else None


def _trash_records(session: Session) -> Iterable[TrashRecord]:
    for model in TRASH_MODELS.values():
        yield from session.exec(select(model).where(model.is_deleted.is_(True)))


@router.get("/items")
def list_trash_items(session: SessionDep) -> list[TrashItemRead]:
    items = []
    for record in _trash_records(session):
        if record.deleted_at is None:
            continue
        if isinstance(record, Document):
            kind, title, details = (
                "document",
                record.filename,
                f"Document ID: {record.doc_id}",
            )
        elif isinstance(record, ChatSession):
            kind = "chat"
            title = record.title or "Untitled Conversation"
            details = f"Document: {record.doc_id}" if record.doc_id else "All Documents"
        else:
            kind, title, details = (
                "extract",
                record.schema_name or "Extraction Job",
                f"Status: {record.status}",
            )
        items.append(
            TrashItemRead(
                id=str(record.id),
                type=kind,
                title=title,
                details=details,
                deleted_at=record.deleted_at,
            )
        )
    return sorted(items, key=lambda item: item.deleted_at, reverse=True)


@router.post("/restore")
def restore_trash_items(session: SessionDep, body: TrashBatchRequest) -> dict[str, int]:
    count = 0
    for item in body.items:
        record = _find_trash_record(session, item)
        if record is not None:
            record.is_deleted = False
            record.deleted_at = None
            count += 1
    session.commit()
    return {"restored": count}


def _purge_records(session: Session, records: list[TrashRecord]) -> int:
    count = 0
    for record in records:
        if not record.is_deleted:
            continue
        path = None
        if isinstance(record, Document):
            path = local_document_path(record)
            other_reference = session.exec(
                select(Document.id).where(
                    Document.doc_id == record.doc_id, Document.id != record.id
                )
            ).first()
            if other_reference is None and record.doc_id != str(record.id):
                with provider_request("document deletion"):
                    client = get_pageindex_client()
                if path is None:
                    try:
                        stored_name = client.get_document(record.doc_id).get("name")
                        path = legacy_document_path(record, stored_name)
                    except Exception:
                        logger.warning(
                            "Could not look up the stored name for document %s",
                            record.id,
                        )
                with provider_request("document deletion", missing_ok=True):
                    client.delete_document(record.doc_id)
        session.delete(record)
        session.commit()
        if path is not None:
            remove_upload(path)
        count += 1
    return count


@router.post("/permanent-delete")
def permanent_delete_items(
    session: SessionDep, body: TrashBatchRequest
) -> dict[str, int]:
    records = []
    seen = set()
    for item in body.items:
        key = (item.type, item.id)
        if key not in seen:
            seen.add(key)
            if record := _find_trash_record(session, item):
                records.append(record)
    return {"deleted": _purge_records(session, records)}


@router.delete("/empty")
def empty_trash(session: SessionDep) -> dict[str, int]:
    return {"purged": _purge_records(session, list(_trash_records(session)))}
