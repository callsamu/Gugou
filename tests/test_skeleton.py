"""Smoke tests for the skeleton."""

from __future__ import annotations

from typing import Any, cast

import httpx
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


def test_pause_and_resume_proxy_to_frontier(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        calls.append({"url": url, **kwargs})
        return httpx.Response(
            200,
            json={"paused": url.endswith("/pause")},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    with TestClient(app) as client:
        paused = cast(
            Any,
            client.post("/pause"),  # pyright: ignore[reportUnknownMemberType]
        )
        resumed = cast(
            Any,
            client.post("/resume"),  # pyright: ignore[reportUnknownMemberType]
        )

    assert paused.json() == {"paused": True}
    assert resumed.json() == {"paused": False}
    assert [call["url"] for call in calls] == [
        f"{settings.frontier_url}/pause",
        f"{settings.frontier_url}/resume",
    ]


def test_crawl_requests_force_from_frontier(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        calls.append({"url": url, **kwargs})
        return httpx.Response(
            202,
            json={"queued": 1, "skipped": 0},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    with TestClient(app) as client:
        response = cast(
            Any,
            client.post(  # pyright: ignore[reportUnknownMemberType]
                "/crawl",
                json={"url": "https://example.com/page"},
            ),
        )

    assert response.status_code == 202
    assert response.json() == {"url": "https://example.com/page", "queued": True}
    assert calls[0]["url"] == f"{settings.frontier_url}/urls"
    assert calls[0]["json"] == {"urls": ["https://example.com/page"], "force": True}


def test_search_endpoint_dispatches_to_the_searcher(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    class FakeResult:
        def get(self, timeout: float) -> dict[str, object]:
            assert timeout == settings.search_timeout
            return {
                "query": "example",
                "results": [
                    {
                        "id": "id1",
                        "url": "https://example.com/article",
                        "title": "Example",
                        "description": "Example summary",
                    }
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
        "results": [
            {
                "id": "id1",
                "url": "https://example.com/article",
                "title": "Example",
                "description": "Example summary",
            }
        ],
    }
    assert sent["name"] == TaskNames.SEARCH
    assert sent["queue"] == QUEUES["search"]
    assert sent["kwargs"] == {"query": "example", "limit": 20}
