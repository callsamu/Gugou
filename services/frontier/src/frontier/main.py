"""HTTP API for the URL frontier."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import AnyHttpUrl, BaseModel, ConfigDict

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
