"""Tests for :mod:`frontier.frontier`."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

import frontier.frontier as frontier_module
from common.config import settings
from frontier import main as frontier_main
from frontier.db import Url, UrlState, create_db, hash_url
from frontier.frontier import Frontier

URL = "https://example.com/article"
OTHER_URL = "https://example.com/other"
FIRST_URL = "https://example.com/first"
SAME_ORIGIN_URL = "https://example.com/second"
OTHER_ORIGIN_URL = "https://other.example.com/third"


def _engine(path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{path}")
    create_db(engine)
    return engine


def _state(engine: Engine, url: str) -> UrlState | None:
    with Session(engine) as session:
        record = session.get(Url, hash_url(url))
        return None if record is None else record.state


def _wait_for_state(engine: Engine, url: str, state: UrlState, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _state(engine, url) is state:
            return
        time.sleep(0.01)
    raise AssertionError(f"{url} did not reach {state}: {_state(engine, url)}")


def _send_ok(url: str) -> dict[str, Any]:
    return {"url": url, "content_path": "/tmp/page.html"}


def test_add_urls_queues_and_completes(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "frontier.db")
    frontier = Frontier(engine=engine, send=_send_ok)

    frontier.start()
    try:
        assert frontier.add_urls([URL]) == 1
        _wait_for_state(engine, URL, UrlState.COMPLETED)
    finally:
        frontier.stop()


def test_add_urls_skips_seen_urls(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "frontier.db")
    frontier = Frontier(engine=engine, send=_send_ok)

    frontier.start()
    try:
        assert frontier.add_urls([URL]) == 1
        _wait_for_state(engine, URL, UrlState.COMPLETED)
        assert frontier.add_urls([URL]) == 0
    finally:
        frontier.stop()


def test_failed_download_marks_failed(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "frontier.db")

    def send(_url: str) -> dict[str, Any]:
        raise RuntimeError("boom")

    frontier = Frontier(engine=engine, send=send)
    frontier.start()
    try:
        assert frontier.add_urls([URL]) == 1
        _wait_for_state(engine, URL, UrlState.FAILED)
    finally:
        frontier.stop()


def test_non_html_marks_failed(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "frontier.db")

    def send(url: str) -> dict[str, Any]:
        return {"url": url, "content_path": None}

    frontier = Frontier(engine=engine, send=send)
    frontier.start()
    try:
        assert frontier.add_urls([URL]) == 1
        _wait_for_state(engine, URL, UrlState.FAILED)
    finally:
        frontier.stop()


def test_debug_limit_caps_added_urls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(tmp_path / "frontier.db")
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(frontier_module, "DEBUG_URL_LIMIT", 1)

    frontier = Frontier(engine=engine, send=_send_ok)
    frontier.start()
    try:
        assert frontier.add_urls([URL, OTHER_URL]) == 1
        _wait_for_state(engine, URL, UrlState.COMPLETED)
        assert _state(engine, OTHER_URL) is None
    finally:
        frontier.stop()


def test_api_adds_urls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(tmp_path / "frontier.db")
    test_frontier = Frontier(engine=engine, send=_send_ok)
    monkeypatch.setattr(frontier_main, "frontier", test_frontier)

    with TestClient(frontier_main.app) as client:
        first = cast(
            Any,
            client.post("/urls", json={"urls": [URL]}),  # pyright: ignore[reportUnknownMemberType]
        )
        _wait_for_state(engine, URL, UrlState.COMPLETED)
        second = cast(
            Any,
            client.post("/urls", json={"urls": [URL]}),  # pyright: ignore[reportUnknownMemberType]
        )
        third = cast(
            Any,
            client.post(  # pyright: ignore[reportUnknownMemberType]
                "/urls",
                json={"urls": [URL], "force": True},
            ),
        )
        _wait_for_state(engine, URL, UrlState.COMPLETED)

    assert first.status_code == 202
    assert first.json() == {"queued": 1, "skipped": 0}
    assert second.json() == {"queued": 0, "skipped": 1}
    assert third.json() == {"queued": 1, "skipped": 0}


def test_same_origin_urls_are_queued_after_the_delay(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "frontier.db")
    first_started = threading.Event()
    release_first = threading.Event()
    processed: list[str] = []

    def send(url: str) -> dict[str, Any]:
        processed.append(url)
        if url == FIRST_URL:
            first_started.set()
            release_first.wait(timeout=2)
        return {"url": url, "content_path": "/tmp/page.html"}

    frontier = Frontier(engine=engine, send=send)
    frontier.start()
    try:
        assert frontier.add_urls([FIRST_URL]) == 1
        assert first_started.wait(timeout=2)
        assert frontier.add_urls([SAME_ORIGIN_URL, OTHER_ORIGIN_URL]) == 2
        release_first.set()

        _wait_for_state(engine, FIRST_URL, UrlState.COMPLETED)
        _wait_for_state(engine, SAME_ORIGIN_URL, UrlState.COMPLETED)
        _wait_for_state(engine, OTHER_ORIGIN_URL, UrlState.COMPLETED)
    finally:
        release_first.set()
        frontier.stop()

    assert processed == [FIRST_URL, OTHER_ORIGIN_URL, SAME_ORIGIN_URL]


def test_same_origin_batch_gets_incremental_priorities(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "frontier.db")
    blocker = "https://blocker.example.com/first"
    first = "https://batch.example.com/one"
    second = "https://batch.example.com/two"
    third = "https://batch.example.com/three"
    other = "https://other.example.com/one"
    first_started = threading.Event()
    release_first = threading.Event()
    processed: list[str] = []

    def send(url: str) -> dict[str, Any]:
        processed.append(url)
        if url == blocker:
            first_started.set()
            release_first.wait(timeout=2)
        return {"url": url, "content_path": "/tmp/page.html"}

    frontier = Frontier(engine=engine, send=send)
    frontier.start()
    try:
        assert frontier.add_urls([blocker]) == 1
        assert first_started.wait(timeout=2)
        assert frontier.add_urls([first, second, third]) == 3
        assert frontier.add_urls([other]) == 1
        release_first.set()

        for url in (blocker, first, second, third, other):
            _wait_for_state(engine, url, UrlState.COMPLETED)
    finally:
        release_first.set()
        frontier.stop()

    assert processed == [blocker, first, other, second, third]


def test_force_requeues_a_completed_url(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "frontier.db")
    processed: list[str] = []

    def send(url: str) -> dict[str, Any]:
        processed.append(url)
        return {"url": url, "content_path": "/tmp/page.html"}

    frontier = Frontier(engine=engine, send=send)
    frontier.start()
    try:
        assert frontier.add_urls([URL]) == 1
        _wait_for_state(engine, URL, UrlState.COMPLETED)
        assert frontier.add_urls([URL]) == 0
        assert frontier.add_urls([URL], force=True) == 1

        deadline = time.monotonic() + 2
        while len(processed) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert processed == [URL, URL]
        _wait_for_state(engine, URL, UrlState.COMPLETED)
    finally:
        frontier.stop()


def test_force_bypasses_debug_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(tmp_path / "frontier.db")
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(frontier_module, "DEBUG_URL_LIMIT", 0)

    frontier = Frontier(engine=engine, send=_send_ok)
    frontier.start()
    try:
        assert frontier.add_urls([URL]) == 0
        assert frontier.add_urls([URL], force=True) == 1
        _wait_for_state(engine, URL, UrlState.COMPLETED)
    finally:
        frontier.stop()


def test_pause_stops_consumption_until_resume(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "frontier.db")
    processed: list[str] = []

    def send(url: str) -> dict[str, Any]:
        processed.append(url)
        return {"url": url, "content_path": "/tmp/page.html"}

    frontier = Frontier(engine=engine, send=send)
    frontier.start()
    try:
        frontier.pause()
        assert frontier.is_paused

        assert frontier.add_urls([URL]) == 1
        time.sleep(0.1)
        assert processed == []
        assert _state(engine, URL) is UrlState.PENDING

        frontier.resume()
        assert not frontier.is_paused
        _wait_for_state(engine, URL, UrlState.COMPLETED)
        assert processed == [URL]
    finally:
        frontier.stop()


def test_api_pause_and_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(tmp_path / "frontier.db")
    test_frontier = Frontier(engine=engine, send=_send_ok)
    monkeypatch.setattr(frontier_main, "frontier", test_frontier)

    with TestClient(frontier_main.app) as client:
        paused = cast(
            Any,
            client.post("/pause"),  # pyright: ignore[reportUnknownMemberType]
        )
        queued = cast(
            Any,
            client.post(  # pyright: ignore[reportUnknownMemberType]
                "/urls",
                json={"urls": [URL]},
            ),
        )
        time.sleep(0.1)
        assert _state(engine, URL) is UrlState.PENDING
        resumed = cast(
            Any,
            client.post("/resume"),  # pyright: ignore[reportUnknownMemberType]
        )
        _wait_for_state(engine, URL, UrlState.COMPLETED)

    assert paused.json() == {"paused": True}
    assert queued.json() == {"queued": 1, "skipped": 0}
    assert resumed.json() == {"paused": False}


def test_pending_urls_are_reloaded_on_start(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "frontier.db")
    with Session(engine) as session:
        session.add(
            Url(
                url_hash=hash_url(URL),
                url=URL,
                host="example.com",
                state=UrlState.PENDING,
            )
        )
        session.commit()

    frontier = Frontier(engine=engine, send=_send_ok)
    frontier.start()
    try:
        _wait_for_state(engine, URL, UrlState.COMPLETED)
    finally:
        frontier.stop()
