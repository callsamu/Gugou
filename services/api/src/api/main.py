"""HTTP API service."""

from __future__ import annotations

from typing import Any, cast

import httpx
from celery.exceptions import TimeoutError as CeleryTimeoutError  # pyright: ignore[reportMissingTypeStubs]
from celery.result import AsyncResult  # pyright: ignore[reportMissingTypeStubs]
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from common.celery_app import create_app
from common.config import settings
from common.contracts import CrawlRequest, SearchResponse
from common.queues import QUEUES, TaskNames

celery = create_app(
    "api",
    QUEUES["extract"],
    QUEUES["index"],
    QUEUES["search"],
)
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
def crawl(request: CrawlRequest) -> dict[str, object]:
    """Add a URL to the frontier queue."""
    try:
        response = httpx.post(
            f"{settings.frontier_url.rstrip('/')}/urls",
            json={"urls": [str(request.url)]},
            timeout=settings.frontier_timeout,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"frontier unavailable: {exc}") from exc

    payload = response.json()
    return {"url": str(request.url), "queued": bool(payload.get("queued"))}


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
    """Ask the searcher service for matching pages."""
    try:
        result = cast(
            Any,
            celery.send_task(  # pyright: ignore[reportUnknownMemberType]
                TaskNames.SEARCH,
                kwargs={"query": q, "limit": limit},
                queue=QUEUES["search"],
            ),
        )
        payload = result.get(timeout=settings.search_timeout)
    except CeleryTimeoutError as exc:
        raise HTTPException(status_code=504, detail="search timed out") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"search failed: {exc}") from exc

    return SearchResponse.model_validate(payload)
