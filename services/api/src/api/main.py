"""HTTP API service."""

from __future__ import annotations

from typing import Any, cast

from celery.result import AsyncResult  # pyright: ignore[reportMissingTypeStubs]
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from common.celery_app import create_app
from common.config import settings
from common.contracts import CrawlRequest, SearchResponse, SearchResult
from common.documents import document_metadata
from common.queues import QUEUES, TaskNames
from common.sonic import SonicError, SonicSearch

celery = create_app("api", QUEUES["download"], QUEUES["extract"], QUEUES["index"])
app = FastAPI(title="engsoftware API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/crawl", status_code=202)
def crawl(request: CrawlRequest) -> dict[str, str]:
    """Queue a URL for download -> extract -> index."""
    result = cast(
        Any,
        celery.send_task(  # pyright: ignore[reportUnknownMemberType]
            TaskNames.DOWNLOAD,
            kwargs={"url": str(request.url), "tags": request.tags},
            queue=QUEUES["download"],
        ),
    )
    return {"task_id": result.id, "url": str(request.url), "status": "PENDING"}


@app.get("/tasks/{task_id}")
def task_status(task_id: str) -> dict[str, object]:
    result = cast(Any, AsyncResult(task_id, app=celery))
    return {
        "task_id": task_id,
        "status": result.state,
        "result": result.result if result.successful() else None,
    }


@app.get("/search")
def search(
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
) -> SearchResponse:
    """Query Sonic and resolve the matching object ids back to pages."""
    try:
        with SonicSearch(
            settings.sonic_host,
            settings.sonic_port,
            settings.sonic_password,
        ) as sonic:
            ids = sonic.query(
                settings.sonic_collection,
                settings.sonic_bucket,
                q,
                limit=limit,
            )
    except (OSError, SonicError) as exc:
        raise HTTPException(status_code=502, detail=f"search backend unavailable: {exc}") from exc

    metadata = document_metadata(ids)
    results = [
        SearchResult(
            id=doc_id,
            url=metadata.get(doc_id, {}).get("url"),
            title=metadata.get(doc_id, {}).get("title"),
        )
        for doc_id in ids
    ]
    return SearchResponse(query=q, results=results)
