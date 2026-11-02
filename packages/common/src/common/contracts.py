"""Payloads exchanged over the queues."""

from __future__ import annotations

from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class CrawlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: AnyHttpUrl
    tags: list[str] = Field(default_factory=list)


class Extracted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str | None = None
    description: str | None = None
    text: str | None = None
    links: list[str] = Field(default_factory=list)


class StoredUrl(BaseModel):
    """A URL stored in the frontier database."""

    model_config = ConfigDict(extra="forbid")

    url: str
    url_hash: str
    host: str
    state: str
    priority: int
    createdAt: datetime
    updatedAt: datetime


class SearchResult(BaseModel):
    """One search hit, resolved back to the page it belongs to."""

    model_config = ConfigDict(extra="forbid")

    id: str
    url: str | None = None
    title: str | None = None
    description: str | None = None


class SearchResponse(BaseModel):
    """Response returned by ``GET /search``."""

    model_config = ConfigDict(extra="forbid")

    query: str
    results: list[SearchResult] = Field(default_factory=list[SearchResult])
