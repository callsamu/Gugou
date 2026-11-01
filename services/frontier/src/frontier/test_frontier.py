"""Tests for :mod:`frontier.frontier`."""

from __future__ import annotations

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
        response = cast(
            Any,
            client.post("/urls", json={"urls": [URL]}),  # pyright: ignore[reportUnknownMemberType]
        )

    assert response.status_code == 202
    assert response.json() == {"queued": 1, "skipped": 0}
    _wait_for_state(engine, URL, UrlState.COMPLETED)


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
