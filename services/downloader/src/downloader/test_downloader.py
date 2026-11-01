"""Tests for :mod:`downloader.downloader`."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, select

from downloader.db import Url, UrlState, create_db, hash_url
from downloader.downloader import Downloader, FetchResult

URL = "https://example.com/article"
BODY = b"<html>hi</html>"


def _engine(path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{path}")
    create_db(engine)
    return engine


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


def test_saving_a_url_logs_its_state(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    engine = _engine(tmp_path / "urls.db")
    downloader = Downloader(tmp_path / "raw", engine=engine)

    with caplog.at_level(logging.INFO):
        downloader.create_url(URL)

    assert f"saved url {URL} to the database" in caplog.text
    assert "state=pending" in caplog.text


def test_store_writes_a_hashed_file_under_raw_dir(tmp_path: Path) -> None:
    downloader = Downloader(tmp_path / "raw", client=_client())

    path = downloader.store(downloader.fetch(URL))

    expected = tmp_path / "raw" / f"{hash_url(URL)[:16]}.html"
    assert path == expected
    assert path.read_bytes() == BODY


def test_create_url_records_a_pending_url(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "urls.db")
    downloader = Downloader(tmp_path / "raw", engine=engine)

    record = downloader.create_url(URL)

    assert record.url_hash == hash_url(URL)
    assert record.url == URL
    assert record.host == "example.com"
    assert record.state is UrlState.PENDING
    assert record.createdAt.tzinfo is not None

    with Session(engine) as session:
        assert session.get(Url, hash_url(URL)) is not None


def test_mark_completed_and_failed_update_the_state(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "urls.db")
    downloader = Downloader(tmp_path / "raw", engine=engine)
    downloader.create_url(URL)

    downloader.mark_completed(URL)
    with Session(engine) as session:
        record = session.get(Url, hash_url(URL))
        assert record is not None
        assert record.state is UrlState.COMPLETED

    downloader.mark_failed(URL)
    with Session(engine) as session:
        record = session.get(Url, hash_url(URL))
        assert record is not None
        assert record.state is UrlState.FAILED


def test_recording_the_same_url_twice_keeps_one_row(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "urls.db")
    downloader = Downloader(tmp_path / "raw", engine=engine)

    downloader.create_url(URL)
    downloader.mark_completed(URL)
    downloader.create_url(URL)

    with Session(engine) as session:
        records = session.exec(select(Url)).all()
        assert len(records) == 1
        assert records[0].state is UrlState.PENDING


def test_has_seen_compares_the_url_hash(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "urls.db")
    downloader = Downloader(tmp_path / "raw", engine=engine)

    assert not downloader.has_seen(URL)

    downloader.create_url(URL)

    assert downloader.has_seen(URL)
    assert not downloader.has_seen("https://example.com/other")


def test_url_count_tracks_records(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "urls.db")
    downloader = Downloader(tmp_path / "raw", engine=engine)

    assert downloader.url_count() == 0

    downloader.create_url(URL)
    downloader.create_url("https://example.com/other")

    assert downloader.url_count() == 2


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
