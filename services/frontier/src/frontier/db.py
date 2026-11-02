"""Frontier-owned database table: URL records."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import Enum, StrEnum

from sqlalchemy import Column, inspect, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.engine import Engine
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


def hash_url(url: str) -> str:
    """Return the primary key used for a URL."""
    return hashlib.sha256(url.encode()).hexdigest()


def create_db(eng: Engine) -> None:
    SQLModel.metadata.create_all(eng)
    columns = {column["name"] for column in inspect(eng).get_columns("frontier_url")}
    if "priority" not in columns:
        with eng.begin() as connection:
            connection.execute(
                text("ALTER TABLE frontier_url ADD COLUMN priority INTEGER NOT NULL DEFAULT 0")
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_frontier_url_priority ON frontier_url (priority)"
                )
            )


class UrlState(StrEnum):
    """Lifecycle of a URL in the frontier."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


def _url_state_values(enum_cls: type[Enum]) -> list[str]:
    """Persist enum member values rather than their names."""
    return [str(member.value) for member in enum_cls]


class Url(SQLModel, table=True):
    """A URL known to the frontier."""

    __tablename__ = "frontier_url"

    url_hash: str = Field(primary_key=True)
    url: str = Field(unique=True)
    host: str = Field(index=True)
    priority: int = Field(default=0, index=True)
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
