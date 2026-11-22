import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import UniqueConstraint
from sqlmodel import JSON, Field, Relationship, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class WorkspaceRecord(SQLModel):
    owner_id: str | None = Field(
        default=None, foreign_key="workspaceuser.id", index=True
    )


class Collection(WorkspaceRecord, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True)
    pageindex_collection_id: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)

    documents: list["Document"] = Relationship(
        back_populates="collection", cascade_delete=True
    )
    chat_histories: list["ChatHistory"] = Relationship(
        back_populates="collection", cascade_delete=True
    )
    chat_sessions: list["ChatSession"] = Relationship(
        back_populates="collection", cascade_delete=True
    )


class Document(WorkspaceRecord, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    doc_id: str = Field(index=True, description="PageIndex doc_id")
    filename: str
    original_filename: str | None = None
    file_size: int | None = None
    status: str = Field(default="processing")
    processing_error: str | None = None
    collection_id: uuid.UUID | None = Field(default=None, foreign_key="collection.id")
    uploaded_at: datetime = Field(default_factory=utc_now)
    is_deleted: bool = Field(default=False, index=True)
    deleted_at: datetime | None = Field(default=None)
    metadata_: dict[str, Any] | None = Field(default=None, sa_type=JSON)

    collection: Collection | None = Relationship(back_populates="documents")
    chat_histories: list["ChatHistory"] = Relationship(
        back_populates="document", cascade_delete=True
    )
    extract_jobs: list["ExtractJob"] = Relationship(
        back_populates="document", cascade_delete=True
    )


class ChatSession(WorkspaceRecord, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    title: str = Field(default="New Conversation")
    doc_id: str | None = Field(default=None, index=True)
    collection_id: uuid.UUID | None = Field(default=None, foreign_key="collection.id")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    is_deleted: bool = Field(default=False, index=True)
    deleted_at: datetime | None = Field(default=None)

    collection: Collection | None = Relationship(back_populates="chat_sessions")
    messages: list["ChatHistory"] = Relationship(
        back_populates="chat_session", cascade_delete=True
    )


class ChatHistory(WorkspaceRecord, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: str | None = Field(
        default=None, foreign_key="chatsession.id", index=True
    )
    document_id: uuid.UUID | None = Field(default=None, foreign_key="document.id")
    collection_id: uuid.UUID | None = Field(default=None, foreign_key="collection.id")
    question: str
    answer: str
    citations: list[dict[str, Any]] | None = Field(default=None, sa_type=JSON)
    model: str | None = None
    usage: dict[str, int] | None = Field(default=None, sa_type=JSON)
    created_at: datetime = Field(default_factory=utc_now)

    document: Document | None = Relationship(back_populates="chat_histories")
    collection: Collection | None = Relationship(back_populates="chat_histories")
    chat_session: ChatSession | None = Relationship(back_populates="messages")


class ExtractJob(WorkspaceRecord, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    document_id: uuid.UUID | None = Field(default=None, foreign_key="document.id")
    pageindex_job_id: str
    status: str = Field(default="pending")
    processing_error: str | None = None
    background: bool = False
    schema_name: str | None = None
    result: dict[str, Any] | list[Any] | None = Field(default=None, sa_type=JSON)
    usage: dict[str, Any] | None = Field(default=None, sa_type=JSON)
    extract_metadata: dict[str, Any] | None = Field(default=None, sa_type=JSON)
    created_at: datetime = Field(default_factory=utc_now)
    is_deleted: bool = Field(default=False, index=True)
    deleted_at: datetime | None = Field(default=None)

    document: Document | None = Relationship(back_populates="extract_jobs")


class WorkspaceUser(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    username: str = Field(unique=True, index=True)
    first_name: str | None = None
    last_name: str | None = None
    password_hash: str = ""
    email: str | None = Field(default=None, unique=True, index=True)
    email_verified: bool = False


class WorkspaceProviders(SQLModel, table=True):
    user_id: str = Field(
        primary_key=True, foreign_key="workspaceuser.id", ondelete="CASCADE"
    )
    pageindex_key: str | None = None
    pageindex_key_digest: str | None = Field(default=None, unique=True)
    chat_key: str | None = None
    chat_provider: str | None = None
    chat_model: str | None = None


class EmailLink(SQLModel, table=True):
    token_hash: str = Field(primary_key=True)
    purpose: str = Field(index=True)
    email: str
    user_id: str | None = Field(
        default=None, foreign_key="workspaceuser.id", ondelete="CASCADE"
    )
    expires_at: datetime = Field(index=True)


class EmailChange(SQLModel, table=True):
    user_id: str = Field(
        primary_key=True, foreign_key="workspaceuser.id", ondelete="CASCADE"
    )
    email: str
    session_hash: str
    code_hash: str
    expires_at: datetime = Field(index=True)


class OAuthIdentity(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    provider: str = Field(primary_key=True)
    subject: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="workspaceuser.id", index=True, ondelete="CASCADE")


class OAuthFlow(SQLModel, table=True):
    state_hash: str = Field(primary_key=True)
    provider: str
    verifier: str
    nonce: str
    session_hash: str | None = None
    expires_at: datetime = Field(index=True)


class LoginSession(SQLModel, table=True):
    token_hash: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="workspaceuser.id", index=True, ondelete="CASCADE")
    expires_at: datetime = Field(index=True)


class Quota(SQLModel, table=True):
    key: str = Field(primary_key=True)
    window: int = Field(primary_key=True, index=True)
    value: int = 0


class WorkItem(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: str | None = Field(default=None, foreign_key="workspaceuser.id")
    kind: str
    request_key: str | None = Field(default=None, unique=True)
    fingerprint: str
    resource_ids: list[str] = Field(sa_type=JSON)
    payload: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    available_at: datetime = Field(default_factory=utc_now, index=True)
    lease_until: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    failures: int = 0
    done: bool = Field(default=False, index=True)
