from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.database import SessionDep
from app.document_storage import local_document_path, remove_upload
from app.models import Collection
from app.pageindex_clients import get_pageindex_client, provider_request
from app.quota import reserve_provider_request
from app.schemas import CollectionCreate, CollectionRead

router = APIRouter(prefix="/api/v1/collections", tags=["collections"])


@router.post("", response_model=CollectionRead, status_code=201)
def create_collection(session: SessionDep, body: CollectionCreate) -> Collection:
    reserve_provider_request(session)
    with provider_request("collection creation"):
        result = get_pageindex_client().create_collection(body.name)
        provider_id = result["collection"]["id"]

    collection = Collection(name=body.name, pageindex_collection_id=provider_id)
    session.add(collection)
    session.commit()
    return collection


@router.get("", response_model=list[CollectionRead])
def list_collections(session: SessionDep) -> list[Collection]:
    return list(
        session.exec(select(Collection).order_by(Collection.created_at.desc())).all()
    )


@router.get("/{collection_id}", response_model=CollectionRead)
def get_collection(collection_id: UUID, session: SessionDep) -> Collection:
    collection = session.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return collection


@router.delete("/{collection_id}", status_code=204)
def delete_collection(collection_id: UUID, session: SessionDep) -> None:
    collection = get_collection(collection_id, session)
    paths = [path for doc in collection.documents if (path := local_document_path(doc))]
    if collection.pageindex_collection_id:
        with provider_request("collection deletion", missing_ok=True):
            get_pageindex_client().delete_collection(collection.pageindex_collection_id)
    session.delete(collection)
    session.commit()
    for path in paths:
        remove_upload(path)
