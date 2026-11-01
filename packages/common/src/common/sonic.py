"""Sonic clients backed by the ``asonic`` library.

Asonic is asynchronous; these classes expose the small synchronous surface the
Celery workers need. Each operation opens a channel, runs one command and
closes it again.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Coroutine
from typing import Any, Self, cast

from asonic import Client  # pyright: ignore[reportMissingTypeStubs]
from asonic.enums import Channel  # pyright: ignore[reportMissingTypeStubs]

#: Sonic's channel buffer is 20_000 bytes; keep commands comfortably below it.
MAX_TEXT_LENGTH = 10_000


class SonicError(RuntimeError):
    """Raised when Sonic rejects a command or cannot be reached."""


def _prepare(text: str) -> str:
    """Normalise a payload for Sonic's line protocol."""
    return text[:MAX_TEXT_LENGTH].replace("\\", "\\\\").replace("\r", " ").replace("\n", " ")


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    try:
        return asyncio.run(coro)
    except Exception as exc:
        raise SonicError(str(exc)) from exc


class _SonicChannel:
    """Shared settings and lifecycle helpers for the sync wrappers."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1491,
        password: str = "",
        timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout

    async def _connect(self, channel: Channel) -> Client:
        client: Any = Client(self.host, self.port, self.password)
        await client.channel(channel)
        return cast(Client, client)

    @staticmethod
    async def _close(client: Client) -> None:
        with contextlib.suppress(Exception):
            await client.quit()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        pass


class SonicIngest(_SonicChannel):
    """Synchronous client for the Sonic ``ingest`` channel."""

    async def _push(self, collection: str, bucket: str, object_id: str, text: str) -> None:
        async with asyncio.timeout(self.timeout):
            client = await self._connect(Channel.INGEST)
            try:
                await client.push(collection, bucket, object_id, _prepare(text))
            finally:
                await self._close(client)

    def push(self, collection: str, bucket: str, object_id: str, text: str) -> None:
        """Index ``text`` under ``object_id``; Sonic stores no documents itself."""
        _run(self._push(collection, bucket, object_id, text))


class SonicSearch(_SonicChannel):
    """Synchronous client for the Sonic ``search`` channel."""

    async def _query(
        self,
        collection: str,
        bucket: str,
        terms: str,
        limit: int,
        offset: int,
    ) -> list[str]:
        async with asyncio.timeout(self.timeout):
            client = await self._connect(Channel.SEARCH)
            try:
                query: dict[str, Any] = {"limit": limit}
                if offset:
                    query["offset"] = offset
                raw = await client.query(collection, bucket, _prepare(terms), **query)
            finally:
                await self._close(client)
        return [item.decode() for item in raw]

    def query(
        self,
        collection: str,
        bucket: str,
        terms: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[str]:
        """Return the object ids matching ``terms``."""
        return _run(self._query(collection, bucket, terms, limit, offset))
