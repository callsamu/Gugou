"""Tests for :mod:`downloader.downloader`."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import httpx
import pytest

from downloader.downloader import Downloader, FetchResult

URL = "https://example.com/article"
BODY = b"<html>hi</html>"


def _client(
    body: bytes = BODY,
    content_type: str = "text/html",
    status: int = 200,
) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            content=body,
            headers={"content-type": content_type},
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_fetch_returns_body_and_content_type(tmp_path: Path) -> None:
    result = Downloader(raw_dir=tmp_path, client=_client()).fetch(URL)

    assert result.body == BODY
    assert result.content_type == "text/html"
    assert result.size_bytes == len(result.body)


def test_fetch_truncates_the_body_to_max_bytes(tmp_path: Path) -> None:
    downloader = Downloader(tmp_path, max_bytes=4, client=_client(b"0123456789"))

    assert downloader.fetch(URL).body == b"0123"


def test_fetch_raises_on_error_status(tmp_path: Path) -> None:
    with pytest.raises(httpx.HTTPStatusError):
        Downloader(tmp_path, client=_client(status=404)).fetch(URL)


def test_fetch_logs_request_and_success(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        Downloader(raw_dir=tmp_path, client=_client()).fetch(URL)

    assert f"fetching {URL}" in caplog.text
    assert f"fetch succeeded for {URL}" in caplog.text


def test_fetch_logs_failure(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO), pytest.raises(httpx.HTTPStatusError):
        Downloader(tmp_path, client=_client(status=500)).fetch(URL)

    assert f"fetch failed for {URL}" in caplog.text


def test_store_writes_a_hashed_file_under_raw_dir(tmp_path: Path) -> None:
    downloader = Downloader(tmp_path / "raw", client=_client())

    path = downloader.store(downloader.fetch(URL))

    expected = tmp_path / "raw" / f"{hashlib.sha256(URL.encode()).hexdigest()[:16]}.html"
    assert path == expected
    assert path.read_bytes() == BODY


@pytest.mark.parametrize(
    "content_type",
    ["text/html", "text/html; charset=utf-8", "application/xhtml+xml", "TEXT/HTML"],
)
def test_is_html_accepts_html_documents(content_type: str) -> None:
    result = FetchResult(url=URL, body=b"", content_type=content_type)

    assert Downloader.is_html(result)


@pytest.mark.parametrize("content_type", ["application/pdf", "image/png", "text/plain", "", None])
def test_is_html_rejects_other_content_types(content_type: str | None) -> None:
    result = FetchResult(url=URL, body=b"", content_type=content_type)

    assert not Downloader.is_html(result)
