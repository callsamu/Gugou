"""Extractor-owned database: processed content records."""

from __future__ import annotations

import hashlib
from functools import lru_cache

from sqlalchemy.engine import Engine
from sqlmodel import Field, SQLModel, create_engine

from common.config import settings


def hash_url(url: str) -> str:
    """Return the primary key used for a URL."""
    return hashlib.sha256(url.encode()).hexdigest()


@lru_cache
def get_engine() -> Engine:
    """Build the SQLAlchemy engine described by the shared settings."""
    connect_args: dict[str, object] = {}
    if settings.extractor_db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(
        settings.extractor_db_url,
        echo=settings.log_level.upper() == "DEBUG",
        connect_args=connect_args,
    )


def create_db(eng: Engine) -> None:
    SQLModel.metadata.create_all(eng)


class Content(SQLModel, table=True):
    """A content document the extractor has already seen.

    ``url_hash`` is the primary key (one row per URL). ``content_hash``
    is indexed so we can recognise an already-processed body arriving
    from a different URL and skip it.
    """

    url_hash: str = Field(primary_key=True)
    content_path: str
    content_hash: str = Field(index=True)
