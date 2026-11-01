"""Fetching URLs and persisting their raw bodies."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

import httpx
from sqlalchemy import func
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from common.config import settings
from downloader.db import Url, UrlState, create_db, get_engine, hash_url

HTML_CONTENT_TYPES: Final[frozenset[str]] = frozenset({"text/html", "application/xhtml+xml"})


@dataclass(frozen=True, slots=True)
class FetchResult:
    """A downloaded body together with the metadata the extractor needs."""

    url: str
    body: bytes
    content_type: str | None = None

    @property
    def size_bytes(self) -> int:
        return len(self.body)


class Downloader:
    """Fetch remote documents, store their raw bytes and record metadata.

    Settings default to the shared configuration but can be overridden per
    instance, which keeps the class usable in tests and one-off scripts.
    """

    def __init__(
        self,
        raw_dir: str | Path | None = None,
        *,
        timeout: float | None = None,
        max_bytes: int | None = None,
        user_agent: str | None = None,
        client: httpx.Client | None = None,
        engine: Engine | None = None,
    ) -> None:
        self.raw_dir = Path(raw_dir) if raw_dir is not None else Path(settings.raw_storage_dir)
        self.timeout = timeout if timeout is not None else settings.download_timeout
        self.max_bytes = max_bytes if max_bytes is not None else settings.download_max_bytes
        self.user_agent = user_agent if user_agent is not None else settings.user_agent
        self._client = client
        self._engine = engine
        self._schema_ready = False

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def fetch(self, url: str) -> FetchResult:
        """Download ``url``, truncating the body to ``max_bytes``."""
        headers = {"User-Agent": self.user_agent}
        if self._client is not None:
            response = self._client.get(url, headers=headers)
        else:
            with httpx.Client(follow_redirects=True, timeout=self.timeout) as client:
                response = client.get(url, headers=headers)
        response.raise_for_status()
        return FetchResult(
            url=url,
            body=response.content[: self.max_bytes],
            content_type=response.headers.get("content-type"),
        )

    def store(self, result: FetchResult) -> Path:
        """Write the fetched body under ``raw_dir`` and return its path."""
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        path = self.raw_dir / self._filename_for(result.url)
        path.write_bytes(result.body)
        return path

    def has_seen(self, url: str) -> bool:
        """Return True when ``url`` already has a record in the database."""
        self._ensure_schema()
        with Session(self.engine) as session:
            return session.get(Url, hash_url(url)) is not None

    def url_count(self) -> int:
        """Return the number of URLs recorded in the database."""
        self._ensure_schema()
        with Session(self.engine) as session:
            return int(session.exec(select(func.count()).select_from(Url)).one())

    def create_url(self, url: str) -> Url:
        """Record ``url`` as pending, resetting an existing record for a re-crawl."""
        return self._set_state(url, UrlState.PENDING)

    def mark_completed(self, url: str) -> None:
        """Flag a URL whose content was stored successfully."""
        self._set_state(url, UrlState.COMPLETED)

    def mark_failed(self, url: str) -> None:
        """Flag a URL whose download or storage failed."""
        self._set_state(url, UrlState.FAILED)

    def _ensure_schema(self) -> None:
        if not self._schema_ready:
            create_db(self.engine)
            self._schema_ready = True

    def _set_state(self, url: str, state: UrlState) -> Url:
        self._ensure_schema()

        parts = urlsplit(url)
        with Session(self.engine) as session:
            record = session.get(Url, hash_url(url))
            if record is None:
                record = Url(
                    url_hash=hash_url(url),
                    url=url,
                    host=parts.hostname or parts.netloc,
                )
            record.state = state
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    @staticmethod
    def is_html(result: FetchResult) -> bool:
        """Return False unless the response is an HTML document."""
        if result.content_type is None:
            return False
        media_type = result.content_type.partition(";")[0].strip().lower()
        return media_type in HTML_CONTENT_TYPES

    @staticmethod
    def _filename_for(url: str) -> str:
        digest = hashlib.sha256(url.encode()).hexdigest()[:16]
        return f"{digest}.html"
