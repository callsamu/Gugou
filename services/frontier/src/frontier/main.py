"""HTTP API for the URL frontier."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Query
from pydantic import AnyHttpUrl, BaseModel, ConfigDict

from common.contracts import StoredUrl
from frontier.db import UrlState
from frontier.frontier import Frontier

frontier = Frontier()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    frontier.start()
    try:
        yield
    finally:
        frontier.stop()


app = FastAPI(title="URL frontier", version="0.1.0", lifespan=lifespan)


class AddUrlsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    urls: list[AnyHttpUrl]
    force: bool = False


class AddUrlsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queued: int
    skipped: int


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/urls", status_code=202)
def add_urls(request: AddUrlsRequest) -> AddUrlsResponse:
    """Add URLs to the frontier queue."""
    queued = frontier.add_urls([str(url) for url in request.urls], force=request.force)
    return AddUrlsResponse(queued=queued, skipped=len(request.urls) - queued)


@app.get("/urls")
def list_urls(
    status: UrlState | None = None,
    order_by: Literal["priority", "createdAt"] = "createdAt",
    order: Literal["asc", "desc"] = "asc",
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[StoredUrl]:
    """List stored URLs, optionally filtered by status and ordered."""
    records = frontier.list_urls(
        status=status,
        order_by=order_by,
        order=order,
        limit=limit,
        offset=offset,
    )
    return [
        StoredUrl(
            url=record.url,
            url_hash=record.url_hash,
            host=record.host,
            state=record.state.value,
            priority=record.priority,
            createdAt=record.createdAt,
            updatedAt=record.updatedAt,
        )
        for record in records
    ]


@app.get("/queue")
def queue_status() -> dict[str, bool]:
    """Return whether queue consumption is paused."""
    return {"paused": frontier.is_paused}


@app.post("/pause")
def pause() -> dict[str, bool]:
    """Pause queue consumption without rejecting new URLs."""
    frontier.pause()
    return {"paused": frontier.is_paused}


@app.post("/resume")
def resume() -> dict[str, bool]:
    """Resume queue consumption."""
    frontier.resume()
    return {"paused": frontier.is_paused}
