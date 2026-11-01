"""Tests for :mod:`downloader.main`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlmodel import Session, create_engine

from common.queues import QUEUES, TaskNames
from downloader import main
from downloader.db import Url, UrlState, create_db, hash_url
from downloader.downloader import Downloader

URL = "https://example.com/article"


def _downloader(
    raw_dir: Path,
    body: bytes = b"<html></html>",
    content_type: str | None = "text/html",
    status: int = 200,
) -> Downloader:
    headers = {} if content_type is None else {"content-type": content_type}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body, headers=headers, request=request)

    engine = create_engine(f"sqlite:///{raw_dir.parent / 'urls.db'}")
    create_db(engine)
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return Downloader(raw_dir, client=client, engine=engine)


def _state(downloader: Downloader) -> UrlState | None:
    with Session(downloader.engine) as session:
        record = session.get(Url, hash_url(URL))
        return None if record is None else record.state


def test_html_is_stored_completed_and_forwarded(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    downloader = _downloader(raw_dir)
    sent: list[dict[str, Any]] = []

    def fake_send(*args: object, **kwargs: object) -> None:
        sent.append({"args": args, **kwargs})

    content_path = main.process(URL, downloader)

    expected = raw_dir / f"{hash_url(URL)[:16]}.html"
    assert content_path == expected
    assert expected.read_bytes() == b"<html></html>"
    assert _state(downloader) is UrlState.COMPLETED

    main.forward(URL, str(expected), send=fake_send)
    assert sent[0]["args"] == (TaskNames.EXTRACT,)
    assert sent[0]["queue"] == QUEUES["extract"]
    assert sent[0]["kwargs"] == {"url": URL, "content_path": str(expected)}


def test_seen_url_is_skipped_without_fetching(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    downloader = _downloader(raw_dir)
    downloader.create_url(URL)
    downloader.mark_completed(URL)

    content_path = main.process(URL, downloader)

    assert content_path is None
    assert not raw_dir.exists()
    assert _state(downloader) is UrlState.COMPLETED


def test_pending_url_is_skipped_without_resetting_state(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    downloader = _downloader(raw_dir)
    downloader.create_url(URL)

    content_path = main.process(URL, downloader)

    assert content_path is None
    assert not raw_dir.exists()
    assert _state(downloader) is UrlState.PENDING


def test_non_html_is_not_stored_and_marked_failed(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    downloader = _downloader(raw_dir, body=b"%PDF-1.7", content_type="application/pdf")

    content_path = main.process(URL, downloader)

    assert content_path is None
    assert not raw_dir.exists()
    assert _state(downloader) is UrlState.FAILED


def test_http_errors_are_marked_failed_and_reraised(tmp_path: Path) -> None:
    downloader = _downloader(tmp_path / "raw", status=500)

    with pytest.raises(httpx.HTTPStatusError):
        main.process(URL, downloader)

    assert _state(downloader) is UrlState.FAILED
