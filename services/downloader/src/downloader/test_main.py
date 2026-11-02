"""Tests for :mod:`downloader.main`."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import httpx
import pytest

from common.queues import QUEUES, TaskNames
from downloader import main
from downloader.downloader import Downloader
from downloader.robots import RobotsCache

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

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return Downloader(raw_dir, client=client)


def test_html_is_stored_and_forwarded(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    downloader = _downloader(raw_dir)
    sent: list[dict[str, Any]] = []

    def fake_send(*args: object, **kwargs: object) -> None:
        sent.append({"args": args, **kwargs})

    content_path = main.process(URL, downloader)

    expected = raw_dir / f"{hashlib.sha256(URL.encode()).hexdigest()[:16]}.html"
    assert content_path == expected
    assert expected.read_bytes() == b"<html></html>"

    main.forward(URL, str(expected), send=fake_send)
    assert sent[0]["args"] == (TaskNames.EXTRACT,)
    assert sent[0]["queue"] == QUEUES["extract"]
    assert sent[0]["kwargs"] == {"url": URL, "content_path": str(expected)}


def test_non_html_is_not_stored(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    downloader = _downloader(raw_dir, body=b"%PDF-1.7", content_type="application/pdf")

    content_path = main.process(URL, downloader)

    assert content_path is None
    assert not raw_dir.exists()


def test_http_errors_are_reraised(tmp_path: Path) -> None:
    downloader = _downloader(tmp_path / "raw", status=500)

    with pytest.raises(httpx.HTTPStatusError):
        main.process(URL, downloader)


def test_robots_disallowed_url_is_not_fetched(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    downloader = _downloader(raw_dir)

    def robots(origin: str) -> str:
        return "User-agent: *\nDisallow: /article"

    downloader.robots = RobotsCache(robots, "test-agent")

    assert main.process(URL, downloader) is None
    assert not raw_dir.exists()
