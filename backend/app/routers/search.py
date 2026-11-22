from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.database import SessionDep
from app.models import Collection, Document
from app.pageindex_clients import get_search_client, provider_request
from app.quota import reserve_provider_request
from app.schemas import SearchQuestionResult, SearchRequest, SearchResponse

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.post("")
def search_pages(session: SessionDep, body: SearchRequest) -> SearchResponse:
    options = body.model_dump(
        include={"include_text", "top_k", "max_documents"}, exclude_none=True
    )
    documents = select(Document.doc_id).where(
        Document.is_deleted.is_(False), Document.status == "ready"
    )
    if body.document:
        if (
            session.exec(documents.where(Document.doc_id == body.document)).first()
            is None
        ):
            raise HTTPException(status_code=404, detail="Searchable document not found")
        options["document"] = body.document
        document_ids = [body.document]
    else:
        if body.documents:
            documents = documents.where(Document.doc_id.in_(body.documents))
        if body.collection:
            match = Collection.pageindex_collection_id == body.collection
            try:
                local_id = UUID(body.collection)
            except ValueError:
                local_id = None
            if local_id is not None:
                match = match | (Collection.id == local_id)
            collections = select(Collection.id).where(
                match, Collection.deleted_at.is_(None)
            )
            collection_id = session.exec(collections).first()
            if collection_id is None:
                raise HTTPException(status_code=404, detail="Collection not found")
            documents = documents.where(Document.collection_id == collection_id)
        document_ids = list(dict.fromkeys(session.exec(documents).all()))
        if body.documents and set(document_ids) != set(body.documents):
            raise HTTPException(status_code=404, detail="Searchable document not found")
        if not document_ids:
            return SearchResponse(
                results=[
                    SearchQuestionResult(question=question, documents=[])
                    for question in body.questions
                ]
            )
        options["documents"] = document_ids
    session.rollback()

    reserve_provider_request(session)
    with provider_request("search"):
        result = get_search_client().search(body.questions, **options)
        response = SearchResponse.model_validate(result)
        allowed = set(document_ids)
        for match in response.results:
            match.documents = [
                document for document in match.documents if document.doc_id in allowed
            ]
        return response
