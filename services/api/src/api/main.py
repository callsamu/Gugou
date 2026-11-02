"""HTTP API service."""

from __future__ import annotations

from typing import Any, Literal, cast

import httpx
from celery.exceptions import TimeoutError as CeleryTimeoutError  # pyright: ignore[reportMissingTypeStubs]
from celery.result import AsyncResult  # pyright: ignore[reportMissingTypeStubs]
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from common.celery_app import create_app
from common.config import settings
from common.contracts import CrawlRequest, SearchResponse, StoredUrl
from common.queues import QUEUES, TaskNames

celery = create_app(
    "api",
    QUEUES["extract"],
    QUEUES["index"],
    QUEUES["search"],
)
app = FastAPI(title="Gugou API", version="0.1.0")
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
            json={"urls": [str(request.url)], "force": True},
            timeout=settings.frontier_timeout,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"frontier unavailable: {exc}") from exc

    payload = response.json()
    return {"url": str(request.url), "queued": bool(payload.get("queued"))}


@app.get("/urls")
def list_urls(
    status: Literal["pending", "completed", "failed"] | None = None,
    order_by: Literal["priority", "createdAt"] = "createdAt",
    order: Literal["asc", "desc"] = "asc",
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[StoredUrl]:
    """List URLs stored in the frontier."""
    params: dict[str, str | int] = {
        "order_by": order_by,
        "order": order,
        "limit": limit,
        "offset": offset,
    }
    if status is not None:
        params["status"] = status
    try:
        response = httpx.get(
            f"{settings.frontier_url.rstrip('/')}/urls",
            params=params,
            timeout=settings.frontier_timeout,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"frontier unavailable: {exc}") from exc
    return [StoredUrl.model_validate(item) for item in response.json()]


def _post_frontier(path: str) -> dict[str, object]:
    """POST to a frontier control endpoint and return its JSON response."""
    try:
        response = httpx.post(
            f"{settings.frontier_url.rstrip('/')}{path}",
            timeout=settings.frontier_timeout,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"frontier unavailable: {exc}") from exc
    return cast(dict[str, object], response.json())


@app.get("/queue")
def queue_status() -> dict[str, object]:
    """Return whether the frontier queue is paused."""
    try:
        response = httpx.get(
            f"{settings.frontier_url.rstrip('/')}/queue",
            timeout=settings.frontier_timeout,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"frontier unavailable: {exc}") from exc
    return cast(dict[str, object], response.json())


@app.post("/pause")
def pause() -> dict[str, object]:
    """Pause frontier queue consumption while still accepting new URLs."""
    return _post_frontier("/pause")


@app.post("/resume")
def resume() -> dict[str, object]:
    """Resume frontier queue consumption."""
    return _post_frontier("/resume")


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
