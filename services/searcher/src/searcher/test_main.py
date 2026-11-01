"""Tests for :mod:`searcher.main`."""

from __future__ import annotations

import pytest

from common.contracts import SearchResponse
from searcher import main


class FakeSonic:
    def __init__(self, ids: list[str]) -> None:
        self.ids = ids
        self.calls: list[dict[str, object]] = []

    def __enter__(self) -> FakeSonic:
        return self

    def __exit__(self, *exc_info: object) -> None:
        pass

    def query(self, collection: str, bucket: str, terms: str, limit: int = 20) -> list[str]:
        self.calls.append(
            {"collection": collection, "bucket": bucket, "terms": terms, "limit": limit}
        )
        return self.ids


def test_find_resolves_ids_to_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    sonic = FakeSonic(["id1", "missing"])

    def fake_sonic(*args: object, **kwargs: object) -> FakeSonic:
        return sonic

    def fake_metadata(ids: list[str]) -> dict[str, dict[str, str | None]]:
        return {"id1": {"url": "https://example.com/article", "title": "Example"}}

    monkeypatch.setattr(main, "SonicSearch", fake_sonic)
    monkeypatch.setattr(main, "document_metadata", fake_metadata)

    response = main.find("example", limit=5)

    assert isinstance(response, SearchResponse)
    assert response.query == "example"
    assert [result.url for result in response.results] == [
        "https://example.com/article",
        None,
    ]
    assert [result.title for result in response.results] == ["Example", None]
    assert sonic.calls[0]["limit"] == 5


def test_find_wraps_backend_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_sonic(*args: object, **kwargs: object) -> FakeSonic:
        raise OSError("connection refused")

    monkeypatch.setattr(main, "SonicSearch", broken_sonic)

    with pytest.raises(RuntimeError, match="search backend unavailable"):
        main.find("example")
