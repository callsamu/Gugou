"""Tests for :mod:`extractor.main`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, select

from common.config import settings
from common.contracts import Extracted
from common.queues import QUEUES, TaskNames
from extractor import main
from extractor.db import Content, create_db, hash_url
from extractor.extractor import Extractor

URL = "https://example.com/article"
OTHER_URL = "https://other.example.com/mirror"


def _engine(tmp_path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{tmp_path / 'extractor.db'}")
    create_db(engine)
    return engine


def _monkeypatch_engine(monkeypatch: pytest.MonkeyPatch, engine: Engine) -> None:
    monkeypatch.setattr(main, "get_engine", lambda: engine)


def test_process_parses_the_stored_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(tmp_path)
    _monkeypatch_engine(monkeypatch, engine)

    path = tmp_path / "page.html"
    path.write_text("<title>Stored</title><a href='/one'>one</a>", encoding="utf-8")

    extracted = main.process(URL, str(path), Extractor())

    assert extracted is not None
    assert extracted.url == URL
    assert extracted.title == "Stored"
    assert extracted.links == ["/one"]


def test_process_records_the_content_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(tmp_path)
    _monkeypatch_engine(monkeypatch, engine)

    path = tmp_path / "page.html"
    path.write_text("<title>Stored</title>", encoding="utf-8")

    extracted = main.process(URL, str(path), Extractor())

    assert extracted is not None
    with Session(engine) as session:
        record = session.get(Content, hash_url(URL))
    assert record is not None
    assert record.content_path == str(path)
    assert record.content_hash == Extractor().content_hash(str(path))


def test_process_tolerates_a_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(tmp_path)
    _monkeypatch_engine(monkeypatch, engine)

    extracted = main.process(URL, str(tmp_path / "missing.html"), Extractor())

    assert extracted is not None
    assert extracted.url == URL
    assert extracted.title is None
    assert extracted.text == ""
    assert extracted.links == []


def test_process_skips_already_seen_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _engine(tmp_path)
    _monkeypatch_engine(monkeypatch, engine)

    path = tmp_path / "page.html"
    path.write_text("<title>Stored</title>", encoding="utf-8")

    first = main.process(URL, str(path), Extractor())
    assert first is not None

    # Same body, different URL — content hash is already in the table.
    second = main.process(OTHER_URL, str(path), Extractor())
    assert second is None


def test_process_updates_existing_url_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(tmp_path)
    _monkeypatch_engine(monkeypatch, engine)

    old_path = tmp_path / "old.html"
    old_path.write_text("<title>Old</title>", encoding="utf-8")
    main.process(URL, str(old_path), Extractor())

    new_path = tmp_path / "new.html"
    new_path.write_text("<title>New</title>", encoding="utf-8")
    extracted = main.process(URL, str(new_path), Extractor())

    assert extracted is not None
    assert extracted.title == "New"
    with Session(engine) as session:
        records = session.exec(select(Content).where(Content.url_hash == hash_url(URL))).all()
    assert len(records) == 1
    assert records[0].content_path == str(new_path)


def test_forward_queues_the_extracted_document() -> None:
    sent: list[dict[str, Any]] = []

    def fake_send(*args: object, **kwargs: object) -> None:
        sent.append({"args": args, **kwargs})

    extracted = Extracted(url=URL, title="Stored", text="body", links=["/one"])
    main.forward(extracted, send=fake_send)

    assert sent[0]["args"] == (TaskNames.INDEX,)
    assert sent[0]["queue"] == QUEUES["index"]
    assert sent[0]["kwargs"]["payload"]["title"] == "Stored"


def test_links_to_fetch_resolves_filters_and_dedupes() -> None:
    links = [
        "/one",
        "two",
        "https://example.com/three#section",
        "//cdn.example.com/lib",
        "#section",
        "mailto:hi@example.com",
        "javascript:void(0)",
        "  /one  ",
        URL,
        "",
    ]

    assert main.links_to_fetch(URL, links) == [
        "https://example.com/one",
        "https://example.com/two",
        "https://example.com/three",
        "https://cdn.example.com/lib",
    ]


def test_forward_links_posts_to_the_frontier(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        calls.append({"url": url, **kwargs})
        return httpx.Response(
            202,
            json={"queued": 2, "skipped": 0},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    main.forward_links(URL, ["/one", "https://example.com/two", "/one", "mailto:hi@example.com"])

    assert calls == [
        {
            "url": f"{settings.frontier_url}/urls",
            "json": {"urls": ["https://example.com/one", "https://example.com/two"]},
            "timeout": settings.frontier_timeout,
        }
    ]


def test_run_forwards_and_queues_links(monkeypatch: pytest.MonkeyPatch) -> None:
    extracted = Extracted(url=URL, title="Stored", text="body", links=["/one"])
    forwarded: list[Extracted] = []
    queued: list[tuple[str, list[str]]] = []

    def fake_process(url: str, content_path: str | None, extractor: Extractor) -> Extracted:
        return extracted

    def fake_forward(item: Extracted) -> None:
        forwarded.append(item)

    def fake_forward_links(url: str, links: list[str]) -> None:
        queued.append((url, links))

    monkeypatch.setattr(main, "process", fake_process)
    monkeypatch.setattr(main, "forward", fake_forward)
    monkeypatch.setattr(main, "forward_links", fake_forward_links)

    result = main.run(URL, "page.html", Extractor())

    assert result == extracted.model_dump()
    assert forwarded == [extracted]
    assert queued == [(URL, ["/one"])]


def test_run_skips_when_content_was_already_seen(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def fake_process(url: str, content_path: str | None, extractor: Extractor) -> None:
        return None

    def fail(*args: object, **kwargs: object) -> None:
        called.append("called")

    monkeypatch.setattr(main, "process", fake_process)
    monkeypatch.setattr(main, "forward", fail)
    monkeypatch.setattr(main, "forward_links", fail)

    assert main.run(URL, "page.html", Extractor()) is None
    assert called == []
