"""Search worker: indexes documents into Meilisearch and answers search queries."""

from __future__ import annotations

import hashlib
from typing import Any, cast

from common.celery_app import create_app
from common.contracts import Extracted, SearchResponse, SearchResult
from common.meilisearch import SearchError, add_document, search_documents
from common.queues import QUEUES, TaskNames

app = create_app("searcher", QUEUES["index"], QUEUES["search"])


def find(query: str, limit: int = 20) -> SearchResponse:
    """Query Meilisearch and build the shared search response."""
    try:
        hits = search_documents(query, limit)
    except SearchError as exc:
        raise RuntimeError(f"search backend unavailable: {exc}") from exc

    results = [
        SearchResult(
            id=str(hit.get("id", "")),
            url=hit.get("url"),
            title=hit.get("title"),
        )
        for hit in hits
    ]
    return SearchResponse(query=query, results=results)


def index_document(payload: dict[str, Any]) -> dict[str, Any]:
    """Index an extracted document in Meilisearch."""
    document = Extracted.model_validate(payload)
    doc_id = hashlib.sha256(document.url.encode()).hexdigest()[:16]
    add_document(
        {
            "id": doc_id,
            "url": document.url,
            "title": document.title or "",
            "text": document.text or "",
        }
    )
    return {"id": doc_id, "url": document.url}


@cast(Any, app.task)(name=TaskNames.INDEX)  # pyright: ignore[reportUnknownMemberType]
def index(payload: dict[str, Any]) -> dict[str, Any]:
    """Celery entry point used by the extractor."""
    return index_document(payload)


@cast(Any, app.task)(name=TaskNames.SEARCH)  # pyright: ignore[reportUnknownMemberType]
def search(query: str, limit: int = 20) -> dict[str, Any]:
    """Celery entry point used by the API's ``GET /search``."""
    return find(query, limit).model_dump()
