"""Priority URL frontier processed by a background asyncio thread."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from typing import Any, cast
from urllib.parse import urlsplit

from sqlalchemy import func
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from common.celery_app import create_app
from common.config import settings
from common.queues import QUEUES, TaskNames
from frontier.db import Url, UrlState, create_db, get_engine, hash_url

logger = logging.getLogger(__name__)

#: Debug-mode cap on the number of URLs recorded in the frontier.
DEBUG_URL_LIMIT = 2000

#: How long the frontier waits for a download task result.
DOWNLOAD_TASK_TIMEOUT = 60.0

#: Spacing between queued URLs of the same origin, in nanoseconds.
ORIGIN_DELAY_NS = 15 * 1_000_000_000


class Frontier:
    """A priority URL queue ordered by insertion time and backed by SQLite."""

    def __init__(
        self,
        engine: Engine | None = None,
        send: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self._engine = engine
        self._send = send or self._send_download
        self._queue: asyncio.PriorityQueue[tuple[int, str | None]] = asyncio.PriorityQueue()
        self._origins: dict[str, int] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._resume: asyncio.Event | None = None
        self._paused = threading.Event()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._db_lock = threading.RLock()
        self._celery = create_app("frontier", QUEUES["download"])

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def start(self) -> None:
        """Start the background loop and wait until it is ready."""
        if self._thread is not None:
            return
        self._paused.clear()
        self._thread = threading.Thread(target=self._run, name="frontier", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("frontier background loop did not start")

    def stop(self) -> None:
        """Ask the background loop to stop and wait for the thread."""
        loop = self._loop
        thread = self._thread
        if loop is None or thread is None:
            return
        if self._resume is not None:
            loop.call_soon_threadsafe(self._resume.set)
        loop.call_soon_threadsafe(self._queue.put_nowait, (-1, None))
        thread.join(timeout=5)
        self._loop = None
        self._resume = None
        self._thread = None

    @property
    def is_paused(self) -> bool:
        """Return True while queue consumption is paused."""
        return self._paused.is_set()

    def pause(self) -> None:
        """Pause queue consumption; new URLs are still accepted."""
        loop = self._loop
        resume = self._resume
        if loop is None or resume is None:
            raise RuntimeError("frontier is not running")
        self._paused.set()
        loop.call_soon_threadsafe(resume.clear)

    def resume(self) -> None:
        """Resume queue consumption."""
        loop = self._loop
        resume = self._resume
        if loop is None or resume is None:
            raise RuntimeError("frontier is not running")
        self._paused.clear()
        loop.call_soon_threadsafe(resume.set)

    def add_urls(self, urls: list[str], *, force: bool = False) -> int:
        """Persist URLs as pending and enqueue them by insertion time.

        ``force`` is used by manual crawl requests: it re-queues URLs that were
        already seen and bypasses the debug URL cap. Discovered links use the
        default and are deduplicated.
        """
        loop = self._loop
        if loop is None:
            raise RuntimeError("frontier is not running")

        queued: list[tuple[int, str]] = []
        accepted = 0
        created = time.time_ns()
        with self._db_lock:
            for url in urls:
                existing = self._get(url)
                if existing is not None:
                    if not force:
                        logger.info("frontier: skipping %s: url already seen", url)
                        continue
                    if existing.state is UrlState.PENDING:
                        logger.info("frontier: %s is already pending", url)
                        accepted += 1
                        continue
                    self._set_state(url, UrlState.PENDING)
                else:
                    if not force and settings.debug and self._url_count() >= DEBUG_URL_LIMIT:
                        logger.info("frontier: debug url limit of %d reached", DEBUG_URL_LIMIT)
                        break
                    self._insert(url)

                origin = _origin(url)
                previous = self._origins.get(origin)
                priority = created if previous is None else max(created, previous + ORIGIN_DELAY_NS)
                self._origins[origin] = priority
                queued.append((priority, url))
                accepted += 1

        for priority, url in queued:
            loop.call_soon_threadsafe(self._queue.put_nowait, (priority, url))
            logger.info("frontier: queued %s (priority=%d)", url, priority)
        return accepted

    def _run(self) -> None:
        asyncio.run(self._serve())

    async def _serve(self) -> None:
        self._loop = asyncio.get_running_loop()
        resume = asyncio.Event()
        resume.set()
        self._resume = resume
        create_db(self.engine)
        for pending_url, created in self._pending_urls():
            origin = _origin(pending_url)
            previous = self._origins.get(origin)
            priority = created if previous is None else max(created, previous + ORIGIN_DELAY_NS)
            self._origins[origin] = priority
            self._queue.put_nowait((priority, pending_url))
        self._ready.set()

        while True:
            await resume.wait()
            _, url = await self._queue.get()
            if url is None:
                break
            await resume.wait()
            try:
                await self._process(url)
            except Exception:
                logger.exception("frontier: failed to process %s", url)

    async def _process(self, url: str) -> None:
        try:
            payload = await asyncio.to_thread(self._send, url)
        except Exception:
            logger.exception("frontier: download failed for %s", url)
            self._set_state(url, UrlState.FAILED)
            return

        state = UrlState.COMPLETED if payload.get("content_path") else UrlState.FAILED
        self._set_state(url, state)

    def _send_download(self, url: str) -> dict[str, Any]:
        result = cast(
            Any,
            self._celery.send_task(  # pyright: ignore[reportUnknownMemberType]
                TaskNames.DOWNLOAD,
                kwargs={"url": url},
                queue=QUEUES["download"],
            ),
        )
        return cast(dict[str, Any], result.get(timeout=DOWNLOAD_TASK_TIMEOUT))

    def _pending_urls(self) -> list[tuple[str, int]]:
        with self._db_lock, Session(self.engine) as session:
            records = session.exec(
                select(Url).where(Url.state == UrlState.PENDING).order_by(col(Url.createdAt))
            ).all()
        return [
            (record.url, int(record.createdAt.timestamp() * 1_000_000_000)) for record in records
        ]

    def _get(self, url: str) -> Url | None:
        with Session(self.engine) as session:
            return session.get(Url, hash_url(url))

    def _url_count(self) -> int:
        with Session(self.engine) as session:
            return int(session.exec(select(func.count()).select_from(Url)).one())

    def _insert(self, url: str) -> None:
        parts = urlsplit(url)
        with Session(self.engine) as session:
            session.add(
                Url(
                    url_hash=hash_url(url),
                    url=url,
                    host=parts.hostname or parts.netloc,
                    state=UrlState.PENDING,
                )
            )
            session.commit()
        logger.info("frontier: saved url %s (state=%s)", url, UrlState.PENDING.value)

    def _set_state(self, url: str, state: UrlState) -> None:
        with self._db_lock, Session(self.engine) as session:
            record = session.get(Url, hash_url(url))
            if record is None:
                parts = urlsplit(url)
                record = Url(
                    url_hash=hash_url(url),
                    url=url,
                    host=parts.hostname or parts.netloc,
                )
            record.state = state
            session.add(record)
            session.commit()
        logger.info("frontier: saved url %s (state=%s)", url, state.value)


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
