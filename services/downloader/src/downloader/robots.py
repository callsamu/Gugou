"""Robots.txt fetching, caching and policy checks."""

from __future__ import annotations

import logging
from collections.abc import Callable
from urllib.parse import urlsplit

from protego import Protego

logger = logging.getLogger(__name__)


class RobotsDenied(RuntimeError):
    """Raised when robots.txt disallows a URL."""


class RobotsCache:
    """Fetch and cache robots.txt per origin, then check URLs against it."""

    def __init__(self, fetch: Callable[[str], str], user_agent: str) -> None:
        self._fetch = fetch
        self._user_agent = user_agent
        # origin -> (serialized robots.txt, parsed rules)
        self._cache: dict[str, tuple[str, Protego]] = {}

    def allows(self, url: str) -> bool:
        """Return True when ``url`` is allowed by its origin's robots.txt."""
        origin = _origin(url)
        entry = self._cache.get(origin)
        if entry is None:
            text = self._fetch(origin)
            entry = (text, Protego.parse(text))
            self._cache[origin] = entry
        return entry[1].can_fetch(url, self._user_agent)


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
