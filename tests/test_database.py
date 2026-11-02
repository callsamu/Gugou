"""Tests for the shared SQLite database layout."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect
from sqlmodel import create_engine

from extractor.db import Content
from extractor.db import create_db as create_extractor_db
from frontier.db import Url
from frontier.db import create_db as create_frontier_db


def test_services_own_separate_tables_in_one_database(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'gugou.db'}")

    create_frontier_db(engine)
    create_extractor_db(engine)

    tables = set(inspect(engine).get_table_names())
    assert Url.__tablename__ == "frontier_url"
    assert Content.__tablename__ == "extractor_content"
    assert {Url.__tablename__, Content.__tablename__} <= tables
