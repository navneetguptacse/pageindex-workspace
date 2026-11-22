from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, delete, func, select, update

from app.database import SessionDep, lock_auth_transaction
from app.models import ChatHistory, Collection, Document, utc_now
from app.schemas import CollectionCreate, CollectionRead

router = APIRouter(prefix="/api/v1/collections", tags=["collections"])


@router.post("", response_model=CollectionRead, status_code=201)
def create_collection(session: SessionDep, body: CollectionCreate) -> Collection:
    lock_auth_transaction(session)
    existing = session.exec(
        select(Collection).where(Collection.name == body.name)
    ).first()
    if existing is not None:
        detail = (
            "A collection with this name is in Trash."
            if existing.deleted_at is not None
            else "A collection with this name already exists."
        )
        raise HTTPException(409, detail)
    collection = Collection(name=body.name)
    session.add(collection)
    session.commit()
    return collection


@router.get("", response_model=list[CollectionRead])
def list_collections(session: SessionDep) -> list[Collection]:
    return list(
        session.exec(
            select(Collection)
            .where(Collection.deleted_at.is_(None))
            .order_by(Collection.created_at.desc())
        ).all()
    )


def active_collection(session: Session, collection_id: UUID) -> Collection | None:
    collection = session.get(Collection, collection_id)
    return (
        collection if collection is not None and collection.deleted_at is None else None
    )


@router.get("/{collection_id}", response_model=CollectionRead)
def get_collection(collection_id: UUID, session: SessionDep) -> Collection:
    collection = active_collection(session, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return collection


@router.delete("/{collection_id}", status_code=204)
def delete_collection(collection_id: UUID, session: SessionDep) -> None:
    lock_auth_transaction(session)
    collection = get_collection(collection_id, session)
    deleted_at = utc_now()
    session.exec(
        update(Document)
        .where(Document.collection_id == collection_id)
        .values(
            trashed_with_collection=Document.is_deleted.is_(False),
            is_deleted=True,
            deleted_at=func.coalesce(Document.deleted_at, deleted_at),
        )
    )
    for conversation in collection.chat_sessions:
        session.delete(conversation)
    session.exec(delete(ChatHistory).where(ChatHistory.collection_id == collection_id))
    collection.deleted_at = deleted_at
    session.commit()
