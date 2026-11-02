"""Extractor-owned database table: processed content records."""

from __future__ import annotations

import hashlib

from sqlalchemy.engine import Engine
from sqlmodel import Field, SQLModel


def hash_url(url: str) -> str:
    """Return the primary key used for a URL."""
    return hashlib.sha256(url.encode()).hexdigest()


def create_db(eng: Engine) -> None:
    SQLModel.metadata.create_all(eng)


class Content(SQLModel, table=True):
    """A content document the extractor has already seen.

    ``url_hash`` is the primary key (one row per URL). ``content_hash``
    is indexed so we can recognise an already-processed body arriving
    from a different URL and skip it.
    """

    __tablename__ = "extractor_content"

    url_hash: str = Field(primary_key=True)
    content_path: str
    content_hash: str = Field(index=True)
