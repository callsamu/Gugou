"""Tests for :mod:`searcher.main`."""

from __future__ import annotations

from typing import Any

import pytest

from common.contracts import Extracted, SearchResponse
from common.meilisearch import SearchError
from searcher import main


def test_find_builds_search_results(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_search(query: str, limit: int = 20) -> list[dict[str, Any]]:
        calls.append({"query": query, "limit": limit})
        return [
            {
                "id": "id1",
                "url": "https://example.com/article",
                "title": "Example",
                "description": "Example summary",
            },
            {"id": "id2", "url": None, "title": None, "description": None},
        ]

    monkeypatch.setattr(main, "search_documents", fake_search)

    response = main.find("example", limit=5)

    assert isinstance(response, SearchResponse)
    assert response.query == "example"
    assert [result.id for result in response.results] == ["id1", "id2"]
    assert [result.url for result in response.results] == [
        "https://example.com/article",
        None,
    ]
    assert [result.title for result in response.results] == ["Example", None]
    assert [result.description for result in response.results] == [
        "Example summary",
        None,
    ]
    assert calls == [{"query": "example", "limit": 5}]


def test_find_wraps_backend_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_search(query: str, limit: int = 20) -> list[dict[str, Any]]:
        raise SearchError("connection refused")

    monkeypatch.setattr(main, "search_documents", broken_search)

    with pytest.raises(RuntimeError, match="search backend unavailable"):
        main.find("example")


def test_index_document_adds_to_meilisearch(monkeypatch: pytest.MonkeyPatch) -> None:
    added: list[dict[str, Any]] = []

    def fake_add(document: dict[str, Any]) -> None:
        added.append(document)

    monkeypatch.setattr(main, "add_document", fake_add)

    extracted = Extracted(
        url="https://example.com/article",
        title="Example",
        description="Example summary",
        text="Hello world",
        links=[],
    )
    result = main.index_document(extracted.model_dump())

    assert result["url"] == extracted.url
    assert added == [
        {
            "id": result["id"],
            "url": extracted.url,
            "title": "Example",
            "description": "Example summary",
            "text": "Hello world",
        }
    ]
