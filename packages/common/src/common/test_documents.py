"""Tests for :mod:`common.documents`."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import create_engine

from common.documents import document_metadata, remember_document


def _engine(path: Path) -> Engine:
    return create_engine(f"sqlite:///{path}")


def test_remember_and_lookup(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "documents.db")

    remember_document("id1", "https://example.com/article", "Example", engine=engine)

    assert document_metadata(["id1"], engine=engine) == {
        "id1": {"url": "https://example.com/article", "title": "Example"}
    }


def test_remember_updates_an_existing_document(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "documents.db")

    remember_document("id1", "https://example.com/old", "Old", engine=engine)
    remember_document("id1", "https://example.com/new", "New", engine=engine)

    assert document_metadata(["id1"], engine=engine) == {
        "id1": {"url": "https://example.com/new", "title": "New"}
    }


def test_lookup_ignores_unknown_ids(tmp_path: Path) -> None:
    engine = _engine(tmp_path / "documents.db")
    remember_document("id1", "https://example.com", None, engine=engine)

    assert document_metadata(["id1", "missing"], engine=engine) == {
        "id1": {"url": "https://example.com", "title": None}
    }
    assert document_metadata([], engine=engine) == {}
