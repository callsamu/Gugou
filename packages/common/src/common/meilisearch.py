"""Meilisearch client helpers shared by the searcher."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import meilisearch
from meilisearch.index import Index

from common.config import settings


class SearchError(RuntimeError):
    """Raised when Meilisearch rejects a request or cannot be reached."""


@lru_cache
def get_client() -> meilisearch.Client:
    """Return a client for the configured Meilisearch instance."""
    return meilisearch.Client(settings.meilisearch_url, settings.meilisearch_api_key)


def get_index() -> Index:
    """Return the configured document index."""
    return get_client().index(settings.meilisearch_index)


@lru_cache
def _ensure_settings() -> bool:
    """Apply searchable attributes once per worker process."""
    task = get_index().update_searchable_attributes(["title", "description", "text"])
    get_client().wait_for_task(task.task_uid)
    return True


def add_document(document: dict[str, Any]) -> None:
    """Add or replace a document in the index and wait for completion."""
    try:
        _ensure_settings()
        task = get_index().add_documents([document], primary_key="id")
        get_client().wait_for_task(task.task_uid)
    except Exception as exc:
        raise SearchError(f"could not index document: {exc}") from exc


def search_documents(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return the indexed documents matching ``query``."""
    try:
        result = get_index().search(
            query,
            {
                "limit": limit,
                "attributesToRetrieve": ["id", "url", "title", "description"],
            },
        )
    except Exception as exc:
        raise SearchError(f"could not query Meilisearch: {exc}") from exc
    return list(result.get("hits", []))
