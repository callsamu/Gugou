"""Fetching URLs and persisting their raw bodies."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx

from common.config import settings
from downloader.robots import RobotsCache, RobotsDenied

logger = logging.getLogger(__name__)

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
    """Fetch remote documents and store their raw bytes.

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
        robots: RobotsCache | None = None,
    ) -> None:
        self.raw_dir = Path(raw_dir) if raw_dir is not None else Path(settings.raw_storage_dir)
        self.timeout = timeout if timeout is not None else settings.download_timeout
        self.max_bytes = max_bytes if max_bytes is not None else settings.download_max_bytes
        self.user_agent = user_agent if user_agent is not None else settings.user_agent
        self._client = client
        self.robots = robots or RobotsCache(self._fetch_robots, self.user_agent)

    def _fetch_robots(self, origin: str) -> str:
        """Fetch the serialized robots.txt for ``origin``."""
        url = f"{origin}/robots.txt"
        logger.info("fetching robots.txt for %s", origin)
        try:
            if self._client is not None:
                response = self._client.get(url, headers={"User-Agent": self.user_agent})
            else:
                with httpx.Client(follow_redirects=True, timeout=self.timeout) as client:
                    response = client.get(url, headers={"User-Agent": self.user_agent})
        except httpx.HTTPError as exc:
            logger.warning("could not fetch robots.txt for %s: %s", origin, exc)
            return ""

        if response.status_code in (404, 410):
            return ""
        if response.status_code >= 400:
            logger.warning(
                "robots.txt for %s returned %s; allowing all",
                origin,
                response.status_code,
            )
            return ""
        return response.text

    def fetch(self, url: str) -> FetchResult:
        """Download ``url``, truncating the body to ``max_bytes``."""
        if not self.robots.allows(url):
            logger.info("robots.txt disallows %s", url)
            raise RobotsDenied(url)
        logger.info("fetching %s", url)
        headers = {"User-Agent": self.user_agent}
        try:
            if self._client is not None:
                response = self._client.get(url, headers=headers)
            else:
                with httpx.Client(follow_redirects=True, timeout=self.timeout) as client:
                    response = client.get(url, headers=headers)
            response.raise_for_status()
        except Exception as exc:
            logger.error("fetch failed for %s: %s", url, exc)
            raise

        result = FetchResult(
            url=url,
            body=response.content[: self.max_bytes],
            content_type=response.headers.get("content-type"),
        )
        logger.info(
            "fetch succeeded for %s (%d bytes, content-type=%r)",
            url,
            result.size_bytes,
            result.content_type,
        )
        return result

    def store(self, result: FetchResult) -> Path:
        """Write the fetched body under ``raw_dir`` and return its path."""
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        path = self.raw_dir / self._filename_for(result.url)
        path.write_bytes(result.body)
        return path

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
