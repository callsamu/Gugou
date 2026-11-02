"""Parsing stored HTML into structured documents."""

from __future__ import annotations

import hashlib
from pathlib import Path

from bs4 import BeautifulSoup

from common.contracts import Extracted

#: Page chrome that never contributes to the indexed content.
IGNORED_TAGS = ("header", "nav", "aside", "footer")

#: Only these blocks contribute to the indexed text; everything else is noise.
CONTENT_SELECTOR = "h1, h2, h3, h4, h5, h6, p"


def _meta_content(soup: BeautifulSoup, attribute: str, value: str) -> str | None:
    """Return the normalized content of the first matching ``meta`` tag."""
    for meta in soup.find_all("meta"):
        candidate = meta.get(attribute)
        if isinstance(candidate, str) and candidate.lower() == value:
            content = meta.get("content")
            if content:
                return " ".join(str(content).split())
    return None


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
        for ignored in soup.find_all(IGNORED_TAGS):
            ignored.decompose()

        description = _meta_content(soup, "name", "description") or _meta_content(
            soup, "property", "og:description"
        )
        root = soup.find("article") or soup.find("main") or soup
        chunks: list[str] = []
        for node in root.select(CONTENT_SELECTOR):
            for br in node.find_all("br"):
                br.replace_with(" ")
            text = " ".join(node.get_text("").split())
            if text:
                chunks.append(text)

        return Extracted(
            url=url,
            title=soup.title.get_text(strip=True) if soup.title else None,
            description=description,
            text="\n".join(chunks),
            links=[str(anchor["href"]) for anchor in root.find_all("a", href=True)],
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
