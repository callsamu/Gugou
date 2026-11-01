"""HTML extraction worker."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

from sqlmodel import Session, select

from common.celery_app import create_app
from common.contracts import Extracted
from common.queues import QUEUES, TaskNames
from extractor.db import Content, create_db, get_engine, hash_url
from extractor.extractor import Extractor

logger = logging.getLogger(__name__)

app = create_app("extractor", QUEUES["extract"])


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


@cast(Any, app.task)(name=TaskNames.EXTRACT)  # pyright: ignore[reportUnknownMemberType]
def extract(url: str, content_path: str | None = None) -> dict[str, Any] | None:
    """Parse the stored HTML and forward the structured result to the searcher.

    Returns None when the content was already processed and skipped.
    """
    extracted = process(url, content_path, Extractor())
    if extracted is None:
        return None
    forward(extracted)
    return extracted.model_dump()
