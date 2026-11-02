"""Shared SQLite engine setup.

Every service uses the same database file, but each owns a namespaced table
(``frontier_url``, ``extractor_content``, ...).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import create_engine

from common.config import settings


@lru_cache
def get_engine() -> Engine:
    """Build the SQLAlchemy engine described by the shared settings."""
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        # The API and background threads may use separate sessions.
        connect_args["check_same_thread"] = False
        # Wait for another service's write instead of failing immediately.
        connect_args["timeout"] = 30

    engine = create_engine(
        settings.database_url,
        echo=settings.log_level.upper() == "DEBUG",
        connect_args=connect_args,
    )
    if settings.database_url.startswith("sqlite"):
        _enable_sqlite_concurrency(engine)
    return engine


def _enable_sqlite_concurrency(engine: Engine) -> None:
    """Let readers and the single writer coexist across service processes."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
