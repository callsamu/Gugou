"""Tests for :mod:`downloader.robots`."""

from __future__ import annotations

from downloader.robots import RobotsCache

ROBOTS = """
User-agent: *
Disallow: /private
Allow: /private/public
"""


def _no_robots(origin: str) -> str:
    return ""


def _robots(origin: str) -> str:
    return ROBOTS


def test_allows_when_robots_is_missing() -> None:
    cache = RobotsCache(_no_robots, "test-agent")

    assert cache.allows("https://example.com/page")


def test_uses_allow_and_disallow_rules() -> None:
    cache = RobotsCache(_robots, "test-agent")

    assert not cache.allows("https://example.com/private")
    assert cache.allows("https://example.com/private/public")
    assert cache.allows("https://example.com/public")


def test_caches_robots_per_origin() -> None:
    calls: list[str] = []

    def fetch(origin: str) -> str:
        calls.append(origin)
        return ""

    cache = RobotsCache(fetch, "test-agent")
    cache.allows("https://example.com/one")
    cache.allows("https://example.com/two")
    cache.allows("https://other.example.com/three")

    assert calls == ["https://example.com", "https://other.example.com"]
