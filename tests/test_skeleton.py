"""Smoke tests for the skeleton."""

from __future__ import annotations

from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from api.main import app
from common.celery_app import create_app
from common.config import settings
from common.queues import QUEUES, TaskNames


def test_queues_are_distinct() -> None:
    assert len(set(QUEUES.values())) == len(QUEUES)


def test_celery_app_uses_json_serialization() -> None:
    app = create_app("test", QUEUES["download"])
    conf = cast(Any, app.conf)  # pyright: ignore[reportUnknownMemberType]
    assert conf.task_serializer == "json"
    assert conf.task_create_missing_queues is True


def test_task_names_are_namespaced() -> None:
    for name in (TaskNames.DOWNLOAD, TaskNames.EXTRACT, TaskNames.INDEX, TaskNames.SEARCH):
        assert "." in name


def test_api_healthz() -> None:
    with TestClient(app) as client:
        response = cast(Any, client.get("/healthz"))  # pyright: ignore[reportUnknownMemberType]
        assert response.json() == {"status": "ok"}


def test_search_endpoint_dispatches_to_the_searcher(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    class FakeResult:
        def get(self, timeout: float) -> dict[str, object]:
            assert timeout == settings.search_timeout
            return {
                "query": "example",
                "results": [
                    {"id": "id1", "url": "https://example.com/article", "title": "Example"}
                ],
            }

    class FakeCelery:
        def send_task(self, name: str, **kwargs: object) -> FakeResult:
            sent["name"] = name
            sent.update(kwargs)
            return FakeResult()

    monkeypatch.setattr(api_main, "celery", FakeCelery())

    with TestClient(app) as client:
        response = cast(
            Any,
            client.get("/search", params={"q": "example"}),  # pyright: ignore[reportUnknownMemberType]
        )

    assert response.status_code == 200
    assert response.json() == {
        "query": "example",
        "results": [{"id": "id1", "url": "https://example.com/article", "title": "Example"}],
    }
    assert sent["name"] == TaskNames.SEARCH
    assert sent["queue"] == QUEUES["search"]
    assert sent["kwargs"] == {"query": "example", "limit": 20}
