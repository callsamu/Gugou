"""Minimal Sonic Channel clients (ingestion and search).

Sonic speaks a line based TCP protocol. These clients cover the commands the
pipeline needs without pulling in an extra dependency.
"""

from __future__ import annotations

import socket
from typing import Self

#: Sonic's channel buffer is 20_000 bytes; keep commands comfortably below it.
MAX_TEXT_LENGTH = 10_000


class SonicError(RuntimeError):
    """Raised when Sonic answers with an ``ERR`` line."""


def _escape(text: str) -> str:
    """Quote a payload for Sonic's line protocol."""
    return (
        text[:MAX_TEXT_LENGTH]
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", " ")
        .replace("\n", " ")
    )


class _SonicChannel:
    """Shared handshake and command plumbing for Sonic's channels."""

    channel: str = ""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1491,
        password: str = "",
        timeout: float = 10.0,
    ) -> None:
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._reader = self._sock.makefile("r", encoding="utf-8", newline="\n")
        self._writer = self._sock.makefile("w", encoding="utf-8", newline="\n")

        try:
            greeting = self._reader.readline()
            if not greeting.startswith("CONNECTED"):
                raise SonicError(f"unexpected greeting: {greeting.strip()!r}")
            response = self._command(f"START {self.channel} {password}".rstrip())
            if not response.startswith("STARTED"):
                raise SonicError(f"could not open {self.channel} channel: {response!r}")
        except Exception:
            self.close()
            raise

    def _command(self, line: str) -> str:
        self._writer.write(f"{line}\n")
        self._writer.flush()
        response = self._reader.readline().strip()
        if response.startswith("ERR"):
            raise SonicError(response)
        return response

    def close(self) -> None:
        for stream in (self._reader, self._writer):
            stream.close()
        self._sock.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class SonicIngest(_SonicChannel):
    """Blocking client for the Sonic ``ingest`` channel."""

    channel = "ingest"

    def push(self, collection: str, bucket: str, object_id: str, text: str) -> None:
        """Index ``text`` under ``object_id``; Sonic stores no documents itself."""
        self._command(f'PUSH {collection} {bucket} {object_id} "{_escape(text)}"')


class SonicSearch(_SonicChannel):
    """Blocking client for the Sonic ``search`` channel."""

    channel = "search"

    def query(
        self,
        collection: str,
        bucket: str,
        terms: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[str]:
        """Return the object ids matching ``terms``."""
        command = f'QUERY {collection} {bucket} "{_escape(terms)}" LIMIT({limit})'
        if offset:
            command += f" OFFSET({offset})"
        pending = self._command(command)
        if not pending.startswith("PENDING"):
            raise SonicError(f"unexpected query response: {pending!r}")

        _, _, query_id = pending.partition(" ")
        event = self._reader.readline().strip()
        if event.startswith("ERR"):
            raise SonicError(event)

        parts = event.split()
        if len(parts) < 3 or parts[0] != "EVENT" or parts[1] != "QUERY":
            raise SonicError(f"unexpected query event: {event!r}")
        if parts[2] != query_id:
            raise SonicError(f"query id mismatch: {event!r}")
        return parts[3:]
