"""Smoke tests for the skeleton."""

from __future__ import annotations

import socket
import threading
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from api.main import app
from common.celery_app import create_app
from common.config import settings
from common.queues import QUEUES, TaskNames
from common.sonic import SonicIngest, SonicSearch


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


def test_sonic_client_speaks_the_ingest_protocol() -> None:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    received: list[str] = []

    def serve() -> None:
        conn, _ = server.accept()
        with conn, conn.makefile("rw", encoding="utf-8", newline="\n") as stream:
            stream.write("CONNECTED <sonic-server v1.10.2>\n")
            stream.flush()
            received.append(stream.readline().strip())
            stream.write("STARTED ingest protocol(1) buffer(20000)\n")
            stream.flush()
            received.append(stream.readline().strip())
            stream.write("OK\n")
            stream.flush()
            received.append(stream.readline().strip())
            stream.write("ENDED quit\n")
            stream.flush()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        with SonicIngest("127.0.0.1", server.getsockname()[1], "pw") as sonic:
            sonic.push("col", "buc", "id1", 'hello "world"\nnext line')
        thread.join(timeout=2)
    finally:
        server.close()

    assert received == [
        "START ingest pw",
        'PUSH col buc id1 "hello \\"world\\" next line"',
        "QUIT",
    ]


def test_sonic_search_returns_object_ids() -> None:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    received: list[str] = []

    def serve() -> None:
        conn, _ = server.accept()
        with conn, conn.makefile("rw", encoding="utf-8", newline="\n") as stream:
            stream.write("CONNECTED <sonic-server v1.10.2>\n")
            stream.flush()
            received.append(stream.readline().strip())
            stream.write("STARTED search protocol(1) buffer(20000)\n")
            stream.flush()
            received.append(stream.readline().strip())
            stream.write("PENDING 42\n")
            stream.write("EVENT QUERY 42 id1 id2\n")
            stream.flush()
            received.append(stream.readline().strip())
            stream.write("ENDED quit\n")
            stream.flush()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        with SonicSearch("127.0.0.1", server.getsockname()[1], "pw") as sonic:
            ids = sonic.query("col", "buc", "hello", limit=2)
        thread.join(timeout=2)
    finally:
        server.close()

    assert ids == ["id1", "id2"]
    assert received == ["START search pw", 'QUERY col buc "hello" LIMIT(2)', "QUIT"]


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
