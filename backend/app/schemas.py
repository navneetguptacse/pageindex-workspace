from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Question = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
Identifier = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)
]


class CollectionCreate(BaseModel):
    name: Name


class CollectionRead(BaseModel):
    id: uuid.UUID
    name: str
    pageindex_collection_id: str | None = None
    created_at: datetime


class DocumentRename(BaseModel):
    filename: Name

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, filename: str) -> str:
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        if (
            not filename[:-4].strip(" .")
            or not filename.isprintable()
            or "/" in filename
            or "\\" in filename
            or len(filename.encode()) > 200
        ):
            raise ValueError(
                "Enter a PDF name with no path separators and at most 200 bytes"
            )
        return filename


class DocumentMove(BaseModel):
    collection_id: uuid.UUID | None


class DocumentSelection(BaseModel):
    document_ids: list[uuid.UUID] = Field(min_length=1)


class DocumentBatchMove(DocumentSelection, DocumentMove):
    pass


class DocumentRead(BaseModel):
    id: uuid.UUID
    doc_id: str
    filename: str
    file_size: int | None = None
    status: str
    processing_error: str | None = None
    collection_id: uuid.UUID | None = None
    uploaded_at: datetime
    is_deleted: bool = False
    deleted_at: datetime | None = None
    metadata_: dict[str, Any] | None = None


class PagePreviewRead(BaseModel):
    doc_id: str
    filename: str
    page: int
    total_pages: int
    text: str | None = None
    has_image: bool = True
    image_url: str | None = None


class ChatMessageInput(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    question: Question
    doc_id: Identifier | None = None
    collection_id: Identifier | None = None
    session_id: Identifier | None = None
    model: Identifier | None = None
    citations: bool = True
    messages: list[ChatMessageInput] | None = None

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if self.doc_id and self.collection_id:
            raise ValueError("Choose a document or a collection")
        return self


class ChatResponse(BaseModel):
    id: uuid.UUID
    session_id: str | None = None
    question: str
    answer: str
    citations: list[dict[str, Any]] | None = None
    model: str | None = None
    usage: dict[str, int] | None = None
    created_at: datetime


class ChatSessionCreate(BaseModel):
    title: Name | None = None
    doc_id: Identifier | None = None
    collection_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if self.doc_id and self.collection_id:
            raise ValueError("Choose a document or a collection")
        return self


class ChatSessionRead(BaseModel):
    id: str
    title: str
    doc_id: str | None = None
    document_filename: str | None = None
    collection_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message_preview: str | None = None


class ChatBatchDeleteRequest(BaseModel):
    session_ids: list[Identifier] = Field(max_length=200)


class ChatHistoryRead(ChatResponse):
    document_id: uuid.UUID | None = None
    collection_id: uuid.UUID | None = None


class ChatSessionDetail(BaseModel):
    id: str
    title: str
    doc_id: str | None = None
    document_filename: str | None = None
    collection_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[ChatHistoryRead]


class SearchRequest(BaseModel):
    questions: list[Question] = Field(min_length=1, max_length=10)
    document: Identifier | None = None
    documents: list[Identifier] | None = Field(
        default=None, min_length=1, max_length=100
    )
    collection: Identifier | None = None
    include_text: bool = True
    top_k: int | None = Field(default=None, ge=1)
    max_documents: int | None = Field(default=None, ge=1, le=10)

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if (
            sum(
                target is not None
                for target in (self.document, self.documents, self.collection)
            )
            > 1
        ):
            raise ValueError("Choose one search target")
        if self.document is not None and self.max_documents is not None:
            raise ValueError(
                "max_documents is only available for multi-document searches"
            )
        return self


class SearchPageResult(BaseModel):
    page: int
    relevance: float
    read: str | None = None
    text: str | None = None


class SearchDocumentResult(BaseModel):
    doc_id: str = Field(validation_alias=AliasChoices("doc_id", "id"))
    pages: list[SearchPageResult]


class SearchQuestionResult(BaseModel):
    question: str
    documents: list[SearchDocumentResult]


class SearchResponse(BaseModel):
    results: list[SearchQuestionResult]
    usage: dict[str, Any] | None = None


class ExtractRequest(BaseModel):
    document: Identifier
    schema_dict: dict[str, Any] = Field(alias="schema", min_length=1)
    tier: Literal["standard", "pro"] | None = None
    pages: str | None = None
    cite_sources: bool = False
    schema_name: str | None = None


class ExtractJobRead(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID | None = None
    pageindex_job_id: str
    status: str
    processing_error: str | None = None
    schema_name: str | None = None
    result: dict[str, Any] | list[Any] | None = None
    usage: dict[str, Any] | None = None
    extract_metadata: dict[str, Any] | None = None
    created_at: datetime
    is_deleted: bool = False
    deleted_at: datetime | None = None


TrashItemType = Literal["collection", "document", "chat", "extract"]


class TrashItemRef(BaseModel):
    id: Identifier
    type: TrashItemType


class TrashBatchRequest(BaseModel):
    items: list[TrashItemRef] = Field(max_length=200)


class TrashItemRead(TrashItemRef):
    title: str
    details: str | None = None
    deleted_at: datetime
    collection_id: uuid.UUID | None = None
    collection_name: str | None = None
