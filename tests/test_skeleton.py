"""Smoke tests for the skeleton."""

from __future__ import annotations

import socket
import threading
from typing import Any, cast

from fastapi.testclient import TestClient

from api.main import app
from common.celery_app import create_app
from common.queues import QUEUES, TaskNames
from common.sonic import SonicIngest


def test_queues_are_distinct() -> None:
    assert len(set(QUEUES.values())) == len(QUEUES)


def test_celery_app_uses_json_serialization() -> None:
    app = create_app("test", QUEUES["download"])
    conf = cast(Any, app.conf)  # pyright: ignore[reportUnknownMemberType]
    assert conf.task_serializer == "json"
    assert conf.task_create_missing_queues is True


def test_task_names_are_namespaced() -> None:
    for name in (TaskNames.DOWNLOAD, TaskNames.EXTRACT, TaskNames.INDEX):
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
    ]
