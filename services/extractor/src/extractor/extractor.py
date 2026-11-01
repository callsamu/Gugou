"""Parsing stored HTML into structured documents."""

from __future__ import annotations

import hashlib
from pathlib import Path

from bs4 import BeautifulSoup

from common.contracts import Extracted


class Extractor:
    """Turn raw HTML files into the payload the searcher consumes.

    Reading and parsing are separate methods so both can be exercised without
    Celery or the rest of the mesh.
    """

    def __init__(self, parser: str = "html.parser") -> None:
        self.parser = parser

    def load(self, path: str | Path | None) -> str:
        """Read a stored document, returning an empty string when it is missing."""
        if not path:
            return ""
        file = Path(path)
        if not file.exists():
            return ""
        return file.read_text(encoding="utf-8", errors="replace")

    def extract(self, url: str, html: str) -> Extracted:
        """Parse ``html`` into the contract shared with the searcher."""
        soup = BeautifulSoup(html, self.parser)
        return Extracted(
            url=url,
            title=soup.title.get_text(strip=True) if soup.title else None,
            text=soup.get_text(" ", strip=True),
            links=[str(anchor["href"]) for anchor in soup.find_all("a", href=True)],
        )

    def content_hash(self, path: str | Path | None) -> str | None:
        """Hash the raw bytes of the stored document, or None when missing."""
        if not path:
            return None
        file = Path(path)
        if not file.exists():
            return None
        return hashlib.sha256(file.read_bytes()).hexdigest()

    def from_file(self, url: str, path: str | Path | None) -> Extracted:
        """Load and parse a document stored at ``path``."""
        return self.extract(url, self.load(path))
