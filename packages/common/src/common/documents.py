"""SQLite lookup from Sonic object ids to page metadata.

Sonic is an identifier index: it returns object ids, never documents. The
searcher records the matching URL and title here so search tasks can turn hits
back into links. The searcher owns this small SQLite database.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, col, create_engine, select

from common.config import settings


@lru_cache
def get_engine() -> Engine:
    """Build the SQLAlchemy engine described by the shared settings."""
    connect_args: dict[str, object] = {}
    if settings.documents_db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(settings.documents_db_url, connect_args=connect_args)


def create_db(eng: Engine) -> None:
    SQLModel.metadata.create_all(eng)


class Document(SQLModel, table=True):
    """Metadata for a document indexed in Sonic."""

    doc_id: str = Field(primary_key=True)
    url: str
    title: str | None = None


def remember_document(
    doc_id: str,
    url: str,
    title: str | None,
    engine: Engine | None = None,
) -> None:
    """Insert or update the metadata for ``doc_id``."""
    eng = engine or get_engine()
    create_db(eng)
    with Session(eng) as session:
        record = session.get(Document, doc_id)
        if record is None:
            record = Document(doc_id=doc_id, url=url, title=title)
        else:
            record.url = url
            record.title = title
        session.add(record)
        session.commit()


def document_metadata(
    ids: list[str],
    engine: Engine | None = None,
) -> dict[str, dict[str, Any]]:
    """Return the stored metadata for each known ``id``."""
    if not ids:
        return {}
    eng = engine or get_engine()
    create_db(eng)
    with Session(eng) as session:
        records = session.exec(select(Document).where(col(Document.doc_id).in_(ids))).all()
    return {record.doc_id: {"url": record.url, "title": record.title} for record in records}
