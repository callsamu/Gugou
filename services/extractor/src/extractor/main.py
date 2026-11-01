"""HTML extraction worker."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast
from urllib.parse import urldefrag, urljoin, urlsplit

from celery import chunks  # pyright: ignore[reportMissingTypeStubs]
from sqlmodel import Session, select

from common.celery_app import create_app
from common.contracts import Extracted
from common.queues import QUEUES, TaskNames
from extractor.db import Content, create_db, get_engine, hash_url
from extractor.extractor import Extractor

logger = logging.getLogger(__name__)

app = create_app("extractor", QUEUES["extract"])

HTTP_SCHEMES = frozenset({"http", "https"})

#: URLs per chunk task. A chunk downloads its URLs sequentially; chunks run in
#: parallel, so this caps the number of messages and the burst of parallelism.
LINK_CHUNK_SIZE = 10


def links_to_fetch(url: str, links: list[str]) -> list[str]:
    """Resolve, filter and deduplicate the links extracted from ``url``."""
    base, _ = urldefrag(url)
    targets: list[str] = []
    seen: set[str] = set()

    for link in links:
        target, _ = urldefrag(urljoin(base, link.strip()))
        if not target or target == base or target in seen:
            continue
        if urlsplit(target).scheme.lower() not in HTTP_SCHEMES:
            continue
        seen.add(target)
        targets.append(target)

    return targets


def _signature(name: str, **kwargs: Any) -> Any:
    """Create a Celery signature for a task name."""
    return cast(Any, app.signature(name, **kwargs))  # pyright: ignore[reportUnknownMemberType]


def forward_links(
    url: str,
    links: list[str],
    signature: Callable[..., Any] | None = None,
    chunks_factory: Callable[..., Any] | None = None,
) -> None:
    """Queue download work for the links found in ``url`` in chunks.

    A chunk task downloads its URLs sequentially, and the chunks themselves
    run in parallel. This avoids sending one broker message per link when a
    page contains thousands of them.
    """
    targets = links_to_fetch(url, links)
    if not targets:
        return

    make_signature = signature or _signature
    make_chunks = chunks_factory or cast(Callable[..., Any], chunks)
    download = make_signature(TaskNames.DOWNLOAD, queue=QUEUES["download"])
    make_chunks(
        download,
        [(target,) for target in targets],
        LINK_CHUNK_SIZE,
    ).apply_async(queue=QUEUES["download"])
    logger.info(
        "queued %d link(s) from %s in chunks of %d",
        len(targets),
        url,
        LINK_CHUNK_SIZE,
    )


def _already_seen(content_hash: str | None) -> bool:
    """True when this body has already been processed, regardless of URL."""
    if content_hash is None:
        return False
    with Session(get_engine()) as session:
        return (
            session.exec(select(Content).where(Content.content_hash == content_hash)).first()
            is not None
        )


def _record(url: str, content_path: str, content_hash: str) -> None:
    """Insert or update the row for ``url`` with the latest content."""
    with Session(get_engine()) as session:
        record = session.get(Content, hash_url(url))
        if record is None:
            record = Content(
                url_hash=hash_url(url),
                content_path=content_path,
                content_hash=content_hash,
            )
        else:
            record.content_path = content_path
            record.content_hash = content_hash
        session.add(record)
        session.commit()


def process(url: str, content_path: str | None, extractor: Extractor) -> Extracted | None:
    """Parse the stored HTML and build the searcher payload.

    Returns None when the body has already been seen, signalling the caller
    to skip extraction and forwarding.
    """
    create_db(get_engine())
    chk = extractor.content_hash(content_path)
    if _already_seen(chk):
        logger.info("skipping %s: content already processed (hash=%s)", url, chk)
        return None
    extracted = extractor.from_file(url, content_path)
    if chk is not None and content_path is not None:
        _record(url, content_path, chk)
    return extracted


def forward(extracted: Extracted, send: Callable[..., Any] | None = None) -> None:
    """Queue an extracted document for indexing."""
    sender = (
        send if send is not None else cast(Callable[..., Any], app.send_task)  # pyright: ignore[reportUnknownMemberType]
    )
    sender(
        TaskNames.INDEX,
        kwargs={"payload": extracted.model_dump()},
        queue=QUEUES["index"],
    )


def run(url: str, content_path: str | None, extractor: Extractor) -> dict[str, Any] | None:
    """Extract a stored page, forward it and queue the links found in it."""
    extracted = process(url, content_path, extractor)
    if extracted is None:
        return None
    forward(extracted)
    forward_links(url, extracted.links)
    return extracted.model_dump()


@cast(Any, app.task)(name=TaskNames.EXTRACT)  # pyright: ignore[reportUnknownMemberType]
def extract(url: str, content_path: str | None = None) -> dict[str, Any] | None:
    """Parse the stored HTML, forward it and queue the links found in it.

    Returns None when the content was already processed and skipped.
    """
    return run(url, content_path, Extractor())
