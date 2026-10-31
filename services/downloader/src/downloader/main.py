"""URL downloader worker."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from common.celery_app import create_app
from common.queues import QUEUES, TaskNames
from downloader.downloader import Downloader

logger = logging.getLogger(__name__)

app = create_app("downloader", QUEUES["download"])


def process(url: str, downloader: Downloader) -> Path | None:
    """Download ``url``, record its status and return the stored path when HTML."""
    downloader.create_url(url)
    try:
        fetched = downloader.fetch(url)
        if not downloader.is_html(fetched):
            logger.info("not forwarding %s: content type %r is not HTML", url, fetched.content_type)
            downloader.mark_failed(url)
            return None
        content_path = downloader.store(fetched)
    except Exception:
        downloader.mark_failed(url)
        raise
    downloader.mark_completed(url)
    return content_path


def forward(url: str, content_path: str, send: Callable[..., Any] | None = None) -> None:
    """Ask the extractor to parse the stored document."""
    (send or app.send_task)(
        TaskNames.EXTRACT,
        kwargs={"url": url, "content_path": content_path},
        queue=QUEUES["extract"],
    )


@app.task(name=TaskNames.DOWNLOAD)
def download(url: str, tags: list[str] | None = None) -> dict:
    """Fetch the URL, store HTML bodies and forward them to the extractor.

    ``tags`` is part of the crawl request contract; indexing them is not
    implemented yet, so it is accepted and ignored here.
    """
    content_path = process(url, Downloader())
    if content_path is not None:
        forward(url, str(content_path))
    return {"url": url, "content_path": None if content_path is None else str(content_path)}
