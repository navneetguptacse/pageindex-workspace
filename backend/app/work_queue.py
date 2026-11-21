import hashlib
import json
import logging
from datetime import timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import Header, HTTPException
from sqlalchemy import cast, func, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app import database
from app.database import Workspace, WorkspaceSession, current_workspace
from app.document_storage import local_document_path
from app.models import (
    Collection,
    Document,
    ExtractJob,
    WorkItem,
    WorkspaceUser,
    utc_now,
)
from app.pageindex_clients import get_extract_client, get_pageindex_client
from app.provider_settings import ProviderSetupError

logger = logging.getLogger(__name__)
LEASE_TIME = timedelta(minutes=15)
POLL_INTERVAL = timedelta(seconds=5)
RETRY_LIMIT = 4
UPLOAD_REJECTED = "PageIndex could not index this PDF."
SUBMISSION_UNCONFIRMED = (
    "Submission could not be confirmed. Verify the provider before retrying."
)
PENDING_UPLOAD = {"queued", "submitting", "processing"}
IdempotencyKey = Annotated[str | None, Header(min_length=8, max_length=128)]
PENDING_EXTRACTION = {"queued", "submitting", "pending", "running"}


def prefers_background(prefer: str | None) -> bool:
    return prefer is not None and "respond-async" in {
        value.strip().lower() for value in prefer.split(",")
    }


def fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def new_work(
    kind: str, key: str | None, digest: str, ids: list[UUID], **payload: Any
) -> WorkItem:
    workspace = current_workspace.get()
    owner_id = workspace.id if workspace else None
    return WorkItem(
        owner_id=owner_id,
        kind=kind,
        request_key=fingerprint([owner_id, kind, key]) if key else None,
        fingerprint=digest,
        resource_ids=[str(resource_id) for resource_id in ids],
        payload=payload,
    )


def replay_work(session: Session, work: WorkItem) -> WorkItem | None:
    if work.request_key is None:
        return None
    previous = session.exec(
        select(WorkItem).where(WorkItem.request_key == work.request_key)
    ).first()
    if previous and previous.fingerprint != work.fingerprint:
        raise HTTPException(
            status_code=409,
            detail="This idempotency key was already used for a different request",
        )
    return previous


def commit_work(session: Session, work: WorkItem) -> WorkItem | None:
    session.add(work)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        previous = replay_work(session, work)
        if previous is None:
            raise
        return previous
    return None


def retry_upload_status(document: Document) -> str:
    if (
        document.doc_id not in {"", str(document.id)}
        and document.processing_error != UPLOAD_REJECTED
    ):
        return "processing"
    if document.processing_error == SUBMISSION_UNCONFIRMED:
        return "submitting"
    return "queued"


def requeue_upload(session: Session, document: Document) -> None:
    member = str(document.id)
    if session.get_bind().dialect.name == "postgresql":
        includes_document = cast(WorkItem.resource_ids, JSONB).contains([member])
    else:
        resources = func.json_each(WorkItem.resource_ids).table_valued("value")
        includes_document = (
            select(1).select_from(resources).where(resources.c.value == member).exists()
        )

    work_id = session.exec(
        select(WorkItem.id)
        .where(
            WorkItem.kind == "upload",
            WorkItem.owner_id == document.owner_id,
            includes_document,
        )
        .order_by(WorkItem.done, WorkItem.created_at.desc())
        .limit(1)
    ).first()
    if work_id is None:
        session.add(new_work("upload", None, fingerprint([member]), [document.id]))
        return

    now = utc_now()
    requeued = session.exec(
        update(WorkItem)
        .where(
            WorkItem.id == work_id,
            WorkItem.lease_until.is_(None) | (WorkItem.lease_until <= now),
        )
        .values(
            done=False, lease_until=None, available_at=now, created_at=now, failures=0
        )
        .returning(WorkItem.id)
    ).scalar_one_or_none()
    if requeued is None:
        raise HTTPException(
            status_code=409, detail="This upload batch is busy. Try again shortly."
        )


def _claim_work() -> WorkItem | None:
    now = utc_now()
    available = (
        WorkItem.done.is_(False),
        WorkItem.available_at <= now,
        WorkItem.lease_until.is_(None) | (WorkItem.lease_until <= now),
    )
    with Session(database.engine, expire_on_commit=False) as session:
        next_id = session.exec(
            select(WorkItem.id)
            .where(*available)
            .order_by(WorkItem.available_at, WorkItem.id)
            .limit(1)
        ).first()
        if next_id is None:
            return None
        work = session.exec(
            update(WorkItem)
            .where(WorkItem.id == next_id, *available)
            .values(lease_until=now + LEASE_TIME)
            .returning(WorkItem)
        ).scalar_one_or_none()
        session.commit()
        return work


def _resources(session: Session, work: WorkItem) -> list[Document] | list[ExtractJob]:
    model = Document if work.kind == "upload" else ExtractJob
    return list(
        session.exec(
            select(model)
            .where(
                model.id.in_([UUID(value) for value in work.resource_ids]),
                model.status.in_(
                    PENDING_UPLOAD if work.kind == "upload" else PENDING_EXTRACTION
                ),
            )
            .order_by(model.id)
        ).all()
    )


def _fail(resource: Document | ExtractJob, detail: str) -> None:
    resource.status = "failed"
    resource.processing_error = detail


def _upload_step(session: Session, document: Document) -> None:
    client = get_pageindex_client()
    if document.status == "processing":
        result = client.get_document(document.doc_id)
        if result["status"] == "completed":
            document.status = "ready"
        elif result["status"] == "failed":
            _fail(document, UPLOAD_REJECTED)
        return

    path = local_document_path(document)
    if path is None:
        _fail(document, "The uploaded PDF is missing from storage.")
        return

    if document.status == "submitting":
        from pageindex.naming import sanitize_filename

        name = sanitize_filename(path.name)
        provider_id = client.get_document_id(name)
        result = client.get_document(provider_id)
        if result.get("name") != name:
            _fail(
                document,
                "Upload was interrupted. Verify the provider library before retrying.",
            )
            return
        document.doc_id = provider_id
        document.status = "processing"
        return

    collection = (
        session.get(Collection, document.collection_id)
        if document.collection_id
        else None
    )
    options = (
        {"collection_id": collection.pageindex_collection_id}
        if collection and collection.pageindex_collection_id
        else {}
    )
    document.status = "submitting"
    session.commit()
    try:
        result = client.submit_document(str(path), wait=False, **options)
    except Exception as exc:
        if getattr(exc, "status_code", None) == 429:
            document.status = "queued"
        raise
    document.doc_id = result["doc_id"]
    document.status = "processing"


def _apply_extraction(job: ExtractJob, result: dict[str, Any]) -> None:
    job.status = result.get("status") or (
        "completed" if "extract_result" in result else "pending"
    )
    job.result = result.get("extract_result")
    job.usage = result.get("usage")
    job.extract_metadata = result.get("extract_metadata")
    if job.status == "failed":
        job.processing_error = "PageIndex could not complete this extraction."


def _extraction_step(
    session: Session, job: ExtractJob, payload: dict[str, Any]
) -> None:
    if job.status == "submitting":
        _fail(
            job,
            "Extraction submission was interrupted. Verify the provider before retrying.",
        )
        return
    client = get_extract_client()
    if job.pageindex_job_id:
        _apply_extraction(job, client.get_extract(job.pageindex_job_id))
        return

    document = session.get(Document, job.document_id) if job.document_id else None
    if document is None or document.is_deleted or document.status != "ready":
        _fail(job, "The source document is no longer available.")
        return
    job.status = "submitting"
    session.commit()
    try:
        result = client.extract(
            document.doc_id, payload["schema"], wait=False, **payload["options"]
        )
    except Exception as exc:
        if getattr(exc, "status_code", None) == 429:
            job.status = "queued"
        raise
    job.pageindex_job_id = result["id"]
    _apply_extraction(job, result)


def _run_work(session: Session, work: WorkItem) -> None:
    resources = _resources(session, work)
    if not resources:
        work.done = True
        return
    if utc_now() - work.created_at > timedelta(hours=2):
        for resource in resources:
            _fail(
                resource,
                "Processing exceeded its time limit. Check the provider before retrying.",
            )
        work.done = True
        return

    resource = min(
        resources,
        key=lambda item: (item.status != "queued", item.status != "submitting"),
    )
    try:
        if isinstance(resource, Document):
            _upload_step(session, resource)
        else:
            _extraction_step(session, resource, work.payload)
    except Exception as exc:
        work.failures += 1
        status_code = getattr(exc, "status_code", None)
        if isinstance(exc, ProviderSetupError) and resource.status != "submitting":
            _fail(resource, exc.detail)
            work.failures = 0
        elif work.failures >= RETRY_LIMIT or status_code in {
            400,
            401,
            403,
            413,
            415,
            422,
        }:
            detail = (
                SUBMISSION_UNCONFIRMED
                if resource.status == "submitting"
                else "Processing failed. Check the document and workspace provider settings."
            )
            _fail(resource, detail)
            work.failures = 0
        logger.warning(
            "Background %s step failed for %s (%s, status %s)",
            work.kind,
            resource.id,
            type(exc).__name__,
            status_code,
            exc_info=work.owner_id is None,
        )
        work.available_at = utc_now() + POLL_INTERVAL * 2**work.failures
    else:
        work.failures = 0
        work.available_at = utc_now() + (
            timedelta(0)
            if any(item.status == "queued" for item in resources)
            else POLL_INTERVAL
        )


def process_next() -> bool:
    work = _claim_work()
    if work is None:
        return False

    with Session(database.engine) as lookup:
        user = lookup.get(WorkspaceUser, work.owner_id) if work.owner_id else None
        workspace = Workspace(user.id, user.username) if user else None
    if work.owner_id and workspace is None:
        with Session(database.engine) as session:
            work.done = True
            work.lease_until = None
            session.add(work)
            session.commit()
        return True
    context = current_workspace.set(workspace)
    try:
        with WorkspaceSession(
            database.engine, info={"owner_id": work.owner_id}
        ) as session:
            _run_work(session, work)
            work.lease_until = None
            session.add(work)
            session.commit()
    finally:
        current_workspace.reset(context)
    return True
