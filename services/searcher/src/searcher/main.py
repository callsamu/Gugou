"""Search worker: indexes documents into Sonic and answers search queries."""

from __future__ import annotations

import hashlib
from typing import Any, cast

from common.celery_app import create_app
from common.config import settings
from common.contracts import Extracted, SearchResponse, SearchResult
from common.documents import document_metadata, remember_document
from common.queues import QUEUES, TaskNames
from common.sonic import SonicError, SonicIngest, SonicSearch

app = create_app("searcher", QUEUES["index"], QUEUES["search"])


def find(query: str, limit: int = 20) -> SearchResponse:
    """Query Sonic and resolve the matching object ids to pages."""
    try:
        with SonicSearch(
            settings.sonic_host,
            settings.sonic_port,
            settings.sonic_password,
        ) as sonic:
            ids = sonic.query(
                settings.sonic_collection,
                settings.sonic_bucket,
                query,
                limit=limit,
            )
    except (OSError, SonicError) as exc:
        raise RuntimeError(f"search backend unavailable: {exc}") from exc

    metadata = document_metadata(ids)
    results = [
        SearchResult(
            id=doc_id,
            url=metadata.get(doc_id, {}).get("url"),
            title=metadata.get(doc_id, {}).get("title"),
        )
        for doc_id in ids
    ]
    return SearchResponse(query=query, results=results)


@cast(Any, app.task)(name=TaskNames.INDEX)  # pyright: ignore[reportUnknownMemberType]
def index(payload: dict[str, Any]) -> dict[str, Any]:
    """Push the document text to Sonic and remember its metadata."""
    document = Extracted.model_validate(payload)
    doc_id = hashlib.sha256(document.url.encode()).hexdigest()[:16]
    text = "\n".join(part for part in (document.title, document.text) if part)

    with SonicIngest(settings.sonic_host, settings.sonic_port, settings.sonic_password) as sonic:
        sonic.push(settings.sonic_collection, settings.sonic_bucket, doc_id, text)

    remember_document(doc_id, document.url, document.title)

    return {
        "id": doc_id,
        "collection": settings.sonic_collection,
        "bucket": settings.sonic_bucket,
        "url": document.url,
    }


@cast(Any, app.task)(name=TaskNames.SEARCH)  # pyright: ignore[reportUnknownMemberType]
def search(query: str, limit: int = 20) -> dict[str, Any]:
    """Celery entry point used by the API's ``GET /search``."""
    return find(query, limit).model_dump()
