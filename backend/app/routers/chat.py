from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from app.chat_answers import (
    COMPLETE_ANSWER_INSTRUCTIONS,
    ChatAnswer,
    ChatOutputLimitError,
    ModelReply,
    complete_answer,
    document_list_answer,
    is_document_list,
    scoped_answer,
)
from app.chat_context import Prompt, build_prompt, supplied_turns
from app.config import get_settings
from app.database import SessionDep, current_workspace
from app.document_storage import local_document_path
from app.models import ChatHistory, ChatSession, Collection, Document, utc_now
from app.pageindex_clients import get_pageindex_client, provider_request
from app.provider_settings import workspace_chat
from app.quota import record_chat_tokens, reserve_provider_request
from app.schemas import (
    ChatBatchDeleteRequest,
    ChatHistoryRead,
    ChatRequest,
    ChatResponse,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionRead,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


def _lookup_document(session: Session, doc_id: str | None) -> Document | None:
    if doc_id is None:
        return None
    statement = (
        select(Document)
        .where(Document.doc_id == doc_id)
        .order_by(Document.is_deleted, Document.uploaded_at.desc())
    )
    return session.exec(statement).first()


def _active_session(session: Session, session_id: str) -> ChatSession:
    conversation = session.get(ChatSession, session_id)
    if conversation is None or conversation.is_deleted:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return conversation


def _collection_scope(session: Session, identifier: str) -> Collection:
    try:
        local_id = UUID(identifier)
    except ValueError:
        local_id = None
    collection = session.get(Collection, local_id) if local_id else None
    if collection is None:
        collection = session.exec(
            select(Collection).where(Collection.pageindex_collection_id == identifier)
        ).first()
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    if not collection.pageindex_collection_id:
        raise HTTPException(status_code=409, detail="Collection has no PageIndex index")
    return collection


def _agent_answer(
    prompt: Prompt,
    model: str,
    doc_id: str | None,
    collection_id: str | None,
    cites: bool,
    max_turns: int,
    max_tokens: int,
    usage: dict[str, int],
) -> ChatAnswer:
    client = get_pageindex_client()
    options = {
        "citations": cites,
        "doc_id": doc_id,
        "collection_id": collection_id,
        "model": model,
        "max_turns": max_turns,
    }

    def generate(budget: int, retry: bool) -> ModelReply:
        result = client.chat(
            prompt,
            protocol="chat_completions",
            extra_body=None
            if model.startswith("claude-code/")
            else {"max_tokens": budget},
            instructions=COMPLETE_ANSWER_INSTRUCTIONS if retry else None,
            **options,
        )
        choice = result["choices"][0]
        return ModelReply(
            (choice.get("message") or {}).get("content"),
            choice.get("finish_reason"),
            result.get("usage"),
        )

    answer = complete_answer(generate, max_tokens, usage)

    citations = None
    if cites:
        try:
            citations = client.get_citations(answer, doc_id=doc_id)
        except Exception:
            logger.exception("Could not parse PageIndex citations")
    return ChatAnswer(answer, citations)


@router.post("", response_model=ChatResponse, status_code=201)
def chat(session: SessionDep, body: ChatRequest) -> ChatHistory:
    settings = get_settings()
    workspace = current_workspace.get()
    listing_documents = is_document_list(body.question)
    model = None if listing_documents else body.model or settings.chat_model
    if (
        model is not None
        and workspace is None
        and model != settings.chat_model
        and model not in settings.chat_allowed_models
    ):
        raise HTTPException(status_code=422, detail="Chat model is not enabled")

    conversation = (
        _active_session(session, body.session_id) if body.session_id else None
    )
    target_doc_id = body.doc_id or (conversation.doc_id if conversation else None)
    collection_identifier = body.collection_id or (
        str(conversation.collection_id)
        if conversation and conversation.collection_id
        else None
    )
    collection = (
        _collection_scope(session, collection_identifier)
        if collection_identifier
        else None
    )
    local_collection_id = collection.id if collection else None

    if conversation and (target_doc_id, local_collection_id) != (
        conversation.doc_id,
        conversation.collection_id,
    ):
        raise HTTPException(
            status_code=409, detail="Start a new chat to change the document scope"
        )

    document = _lookup_document(session, target_doc_id)
    shared_workspace = workspace is not None
    if target_doc_id and shared_workspace and document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document and document.is_deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    if document and document.status != "ready":
        raise HTTPException(status_code=409, detail="Document is not ready for chat")
    local_document_id = document.id if document else None

    scope = [Document.is_deleted.is_(False), Document.status == "ready"]
    if target_doc_id:
        scope.append(Document.doc_id == target_doc_id)
    elif local_collection_id:
        scope.append(Document.collection_id == local_collection_id)

    inventory = []
    scoped_document_ids = []
    provider = None
    if listing_documents:
        documents = session.exec(
            select(Document).where(*scope).order_by(Document.filename, Document.id)
        ).all()
        inventory = [(row.filename, local_document_path(row)) for row in documents]
    elif workspace is not None:
        provider = workspace_chat(session, workspace)
        if body.model and body.model != provider.model:
            raise HTTPException(
                status_code=422, detail="Choose the chat model in Account settings."
            )
        model = provider.model
        scoped_document_ids = list(
            dict.fromkeys(session.exec(select(Document.doc_id).where(*scope)).all())
        )

    prompt: Prompt = body.question
    if model is not None:
        if conversation:
            recent_turns = session.exec(
                select(ChatHistory.question, ChatHistory.answer)
                .where(ChatHistory.session_id == conversation.id)
                .order_by(ChatHistory.created_at.desc(), ChatHistory.id.desc())
                .limit(settings.chat_history_turns + settings.chat_summary_turns)
            ).all()
        else:
            recent_turns = supplied_turns(body.messages or [])
        prompt = build_prompt(body.question, recent_turns, settings, model)

    title = body.question.splitlines()[0][:60]
    if conversation is None:
        conversation = ChatSession(
            title=title, doc_id=target_doc_id, collection_id=local_collection_id
        )
        previous_update = None
    else:
        previous_update = conversation.updated_at
        if conversation.title not in ("New Conversation", "New Chat", ""):
            title = conversation.title
    session_id = conversation.id
    cloud_collection_id = collection.pageindex_collection_id if collection else None
    session.rollback()

    usage: dict[str, int] = {}
    if model is None:
        reply = document_list_answer(inventory)
    else:
        if not shared_workspace or scoped_document_ids:
            reserve_provider_request(session, chat=True)
        try:
            with provider_request("chat"):
                try:
                    if provider is not None:
                        reply = scoped_answer(
                            prompt,
                            body.question,
                            scoped_document_ids,
                            model,
                            body.citations,
                            settings,
                            usage,
                            api_key=provider.api_key.get_secret_value(),
                        )
                    else:
                        reply = _agent_answer(
                            prompt,
                            model,
                            target_doc_id,
                            cloud_collection_id,
                            body.citations,
                            settings.chat_max_turns,
                            settings.chat_output_tokens,
                            usage,
                        )
                except ChatOutputLimitError as exc:
                    raise HTTPException(
                        status_code=502,
                        detail="The model could not finish a complete answer. Try asking about one part at a time.",
                    ) from exc
        finally:
            if usage:
                record_chat_tokens(
                    session,
                    usage.get("total_tokens")
                    or (
                        usage.get("prompt_tokens", 0)
                        + usage.get("completion_tokens", 0)
                    ),
                )

    now = utc_now()
    if previous_update is None:
        conversation.updated_at = now
        session.add(conversation)
    else:
        result = session.exec(
            update(ChatSession)
            .where(
                ChatSession.id == session_id,
                ChatSession.is_deleted.is_(False),
                ChatSession.updated_at == previous_update,
            )
            .values(title=title, updated_at=now)
        )
        if result.rowcount != 1:
            raise HTTPException(
                status_code=409,
                detail="Chat session changed while answering. Retry the request.",
            )

    record = ChatHistory(
        session_id=session_id,
        document_id=local_document_id,
        collection_id=local_collection_id,
        question=body.question,
        answer=reply.text,
        citations=reply.citations,
        model=model,
        usage=usage or None,
        created_at=now,
    )
    session.add(record)
    try:
        session.commit()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Chat scope changed while answering"
        ) from exc
    return record


@router.get("/sessions")
def list_sessions(
    session: SessionDep,
    doc_id: str | None = None,
    collection_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ChatSessionRead]:
    count = (
        select(func.count(ChatHistory.id))
        .where(ChatHistory.session_id == ChatSession.id)
        .correlate(ChatSession)
        .scalar_subquery()
    )
    preview = (
        select(func.substr(ChatHistory.answer, 1, 120))
        .where(ChatHistory.session_id == ChatSession.id)
        .order_by(ChatHistory.created_at.desc(), ChatHistory.id.desc())
        .limit(1)
        .correlate(ChatSession)
        .scalar_subquery()
    )
    filename = (
        select(Document.filename)
        .where(Document.doc_id == ChatSession.doc_id)
        .order_by(Document.uploaded_at.desc(), Document.id.desc())
        .limit(1)
        .correlate(ChatSession)
        .scalar_subquery()
    )
    statement = (
        select(ChatSession, filename, count, preview)
        .where(ChatSession.is_deleted.is_(False))
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        .limit(limit)
    )
    if doc_id:
        statement = statement.where(ChatSession.doc_id == doc_id)
    if collection_id:
        statement = statement.where(ChatSession.collection_id == collection_id)

    return [
        ChatSessionRead.model_validate(
            conversation,
            from_attributes=True,
        ).model_copy(
            update={
                "document_filename": document_filename,
                "message_count": turn_count * 2,
                "last_message_preview": last_preview,
            }
        )
        for conversation, document_filename, turn_count, last_preview in session.exec(
            statement
        )
    ]


@router.post("/sessions", status_code=201)
def create_session(session: SessionDep, body: ChatSessionCreate) -> ChatSessionRead:
    if body.collection_id:
        _collection_scope(session, str(body.collection_id))
    document = _lookup_document(session, body.doc_id)
    if body.doc_id and current_workspace.get() is not None and document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document and document.is_deleted:
        raise HTTPException(status_code=404, detail="Document not found")

    conversation = ChatSession(
        title=body.title or "New Conversation",
        doc_id=body.doc_id,
        collection_id=body.collection_id,
    )
    session.add(conversation)
    session.commit()
    return ChatSessionRead.model_validate(
        conversation, from_attributes=True
    ).model_copy(update={"document_filename": document.filename if document else None})


@router.get("/sessions/{session_id}")
def get_session_detail(session_id: str, session: SessionDep) -> ChatSessionDetail:
    conversation = _active_session(session, session_id)
    document = _lookup_document(session, conversation.doc_id)
    messages = session.exec(
        select(ChatHistory)
        .where(ChatHistory.session_id == session_id)
        .order_by(ChatHistory.created_at, ChatHistory.id)
    ).all()
    return ChatSessionDetail(
        **conversation.model_dump(exclude={"deleted_at", "is_deleted"}),
        document_filename=document.filename if document else None,
        messages=[
            ChatHistoryRead.model_validate(message, from_attributes=True)
            for message in messages
        ],
    )


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, session: SessionDep) -> None:
    conversation = _active_session(session, session_id)
    conversation.is_deleted = True
    conversation.deleted_at = utc_now()
    session.commit()


@router.post("/sessions/batch-delete")
def batch_delete_sessions(
    session: SessionDep, body: ChatBatchDeleteRequest
) -> dict[str, int]:
    result = session.exec(
        update(ChatSession)
        .where(ChatSession.id.in_(body.session_ids), ChatSession.is_deleted.is_(False))
        .values(is_deleted=True, deleted_at=utc_now())
    )
    session.commit()
    return {"deleted": result.rowcount}


@router.get("/history", response_model=list[ChatHistoryRead])
def chat_history(
    session: SessionDep,
    session_id: str | None = None,
    doc_id: str | None = None,
    collection_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ChatHistory]:
    statement = (
        select(ChatHistory)
        .outerjoin(ChatSession, ChatHistory.session_id == ChatSession.id)
        .where(ChatHistory.session_id.is_(None) | ChatSession.is_deleted.is_(False))
        .order_by(ChatHistory.created_at.desc(), ChatHistory.id.desc())
        .limit(limit)
    )
    if session_id:
        statement = statement.where(ChatHistory.session_id == session_id)
    if doc_id:
        document = _lookup_document(session, doc_id)
        if document is None or document.is_deleted:
            return []
        statement = statement.where(ChatHistory.document_id == document.id)
    if collection_id:
        statement = statement.where(ChatHistory.collection_id == collection_id)

    history = list(session.exec(statement).all())
    return history[::-1] if session_id else history
