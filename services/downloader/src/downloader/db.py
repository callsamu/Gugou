"""Downloader-owned database: URL records and engine setup."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import Enum, StrEnum
from functools import lru_cache

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlalchemy.engine import Engine
from sqlmodel import Field, SQLModel, create_engine

from common.config import settings


def _utcnow() -> datetime:
    return datetime.now(UTC)


def hash_url(url: str) -> str:
    """Return the primary key used for a URL."""
    return hashlib.sha256(url.encode()).hexdigest()


@lru_cache
def get_engine() -> Engine:
    """Build the SQLAlchemy engine described by the shared settings."""
    connect_args: dict[str, object] = {}
    if settings.downloader_db_url.startswith("sqlite"):
        # The API serves requests from a thread pool, so connections may move between threads.
        connect_args["check_same_thread"] = False
    return create_engine(
        settings.downloader_db_url,
        echo=settings.log_level.upper() == "DEBUG",
        connect_args=connect_args,
    )


def create_db(eng: Engine) -> None:
    SQLModel.metadata.create_all(eng)


class UrlState(StrEnum):
    """Download lifecycle of a URL."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


def _url_state_values(enum_cls: type[Enum]) -> list[str]:
    """Persist enum member values rather than their names."""
    return [str(member.value) for member in enum_cls]


class Url(SQLModel, table=True):
    """A URL known to the downloader."""

    url_hash: str = Field(primary_key=True)
    url: str = Field(unique=True)
    host: str = Field(index=True)
    state: UrlState = Field(
        default=UrlState.PENDING,
        sa_column=Column(
            SAEnum(
                UrlState,
                values_callable=_url_state_values,
                name="urlstate",
            ),
            nullable=False,
            index=True,
        ),
    )
    updatedAt: datetime = Field(default_factory=_utcnow, sa_column_kwargs={"onupdate": _utcnow})
    createdAt: datetime = Field(default_factory=_utcnow)
