from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Response
from sqlalchemy import update
from sqlmodel import Session, select

from app.database import SessionDep
from app.models import Document, ExtractJob, WorkItem, utc_now
from app.pageindex_clients import get_extract_client, provider_request
from app.quota import reserve_provider_request
from app.schemas import ExtractJobRead, ExtractRequest
from app.work_queue import (
    IdempotencyKey,
    commit_work,
    fingerprint,
    new_work,
    prefers_background,
    replay_work,
)

router = APIRouter(prefix="/api/v1/extract", tags=["extract"])


@router.post(
    "",
    response_model=ExtractJobRead,
    status_code=201,
    responses={202: {"description": "Extraction queued"}},
)
def extract(
    session: SessionDep,
    body: ExtractRequest,
    response: Response,
    prefer: Annotated[str | None, Header()] = None,
    idempotency_key: IdempotencyKey = None,
) -> ExtractJob:
    statement = select(Document).where(
        Document.doc_id == body.document, Document.is_deleted.is_(False)
    )
    document = session.exec(statement).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.status != "ready":
        raise HTTPException(
            status_code=409, detail="Document is not ready for extraction"
        )
    document_id = document.id
    provider_id = document.doc_id
    session.rollback()

    options = body.model_dump(
        include={"tier", "pages", "cite_sources"}, exclude_none=True
    )
    if prefers_background(prefer):
        response.status_code = 202
        response.headers["Preference-Applied"] = "respond-async"
        job = ExtractJob(
            document_id=document_id,
            pageindex_job_id="",
            status="queued",
            background=True,
            schema_name=body.schema_name,
        )
        work = new_work(
            "extract",
            idempotency_key,
            fingerprint(body.model_dump(mode="json")),
            [job.id],
            schema=body.schema_dict,
            options=options,
        )
        return _enqueue_extraction(session, job, work)

    reserve_provider_request(session)
    with provider_request("extraction"):
        result = get_extract_client().extract(provider_id, body.schema_dict, **options)
        job = ExtractJob(
            document_id=document_id,
            pageindex_job_id=result["id"],
            status=result.get("status")
            or ("completed" if "extract_result" in result else "pending"),
            schema_name=body.schema_name,
            result=result.get("extract_result"),
            usage=result.get("usage"),
            extract_metadata=result.get("extract_metadata"),
        )

    session.add(job)
    session.commit()
    return job


def _enqueue_extraction(
    session: Session, job: ExtractJob, work: WorkItem
) -> ExtractJob:
    previous = replay_work(session, work)
    if previous is None:
        reserve_provider_request(session, commit=False)
        session.add(job)
        previous = commit_work(session, work)
        if previous is None:
            return job

    existing = session.get(ExtractJob, UUID(previous.resource_ids[0]))
    if existing is None or existing.is_deleted:
        raise HTTPException(
            status_code=410, detail="The previous extraction has been deleted"
        )
    return existing


@router.get("/jobs", response_model=list[ExtractJobRead])
def list_jobs(session: SessionDep, document_id: UUID | None = None) -> list[ExtractJob]:
    statement = select(ExtractJob).where(ExtractJob.is_deleted.is_(False))
    if document_id:
        statement = statement.where(ExtractJob.document_id == document_id)
    return list(session.exec(statement.order_by(ExtractJob.created_at.desc())).all())


def _active_job(job_id: UUID, session: SessionDep) -> ExtractJob:
    job = session.get(ExtractJob, job_id)
    if job is None or job.is_deleted:
        raise HTTPException(status_code=404, detail="Extract job not found")
    return job


@router.get("/jobs/{job_id}", response_model=ExtractJobRead)
def get_job(job_id: UUID, session: SessionDep) -> ExtractJob:
    job = _active_job(job_id, session)
    if job.background or job.status not in {"pending", "running"}:
        return job

    provider_id, previous_status = job.pageindex_job_id, job.status
    session.rollback()
    with provider_request("extraction status"):
        result = get_extract_client().get_extract(provider_id)
        status = result["status"]
    if status != previous_status and status != "pending":
        session.exec(
            update(ExtractJob)
            .where(
                ExtractJob.id == job_id,
                ExtractJob.is_deleted.is_(False),
                ExtractJob.status == previous_status,
            )
            .values(
                status=status,
                result=result.get("extract_result"),
                usage=result.get("usage"),
                extract_metadata=result.get("extract_metadata"),
            )
        )
        session.commit()
    return _active_job(job_id, session)


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: UUID, session: SessionDep) -> None:
    job = _active_job(job_id, session)
    job.is_deleted = True
    job.deleted_at = utc_now()
    session.commit()


@router.delete("/jobs")
def clear_jobs(session: SessionDep, document_id: UUID | None = None) -> dict[str, int]:
    statement = update(ExtractJob).where(ExtractJob.is_deleted.is_(False))
    if document_id:
        statement = statement.where(ExtractJob.document_id == document_id)
    result = session.exec(statement.values(is_deleted=True, deleted_at=utc_now()))
    session.commit()
    return {"cleared": result.rowcount}
