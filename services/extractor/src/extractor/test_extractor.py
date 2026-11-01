"""Tests for :mod:`extractor.extractor`."""

from __future__ import annotations

from pathlib import Path

from extractor.extractor import Extractor

URL = "https://example.com/article"
HTML = """\
<html>
  <head><title>Example</title></head>
  <body>
    <p>Hello <b>world</b></p>
    <a href="/one">one</a>
    <a>no href</a>
    <a href="https://example.com/two">two</a>
  </body>
</html>
"""


def test_extract_builds_the_shared_contract() -> None:
    extracted = Extractor().extract(URL, HTML)

    assert extracted.url == URL
    assert extracted.title == "Example"
    assert extracted.text is not None
    assert "Hello world" in extracted.text
    assert extracted.links == ["/one", "https://example.com/two"]


def test_extract_without_a_title() -> None:
    extracted = Extractor().extract(URL, "<p>no title here</p>")

    assert extracted.title is None


def test_extract_keeps_only_title_h1_and_paragraphs() -> None:
    html = """
    <html><head><title>Page title</title></head><body>
      <h1>Main heading</h1>
      <div>navigation noise</div>
      <p>First <b>paragraph</b>.</p>
      <ul><li>list noise</li></ul>
      <h2>Subheading</h2>
      <p>Second paragraph.</p>
    </body></html>
    """

    extracted = Extractor().extract(URL, html)

    assert extracted.text == "Page title\nMain heading\nFirst paragraph.\nSecond paragraph."
    assert "Subheading" not in extracted.text
    assert "noise" not in extracted.text


def test_extract_returns_empty_text_without_content_nodes() -> None:
    extracted = Extractor().extract(URL, "<div>only noise</div>")

    assert extracted.text == ""


def test_load_reads_html_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    path.write_text(HTML, encoding="utf-8")

    extractor = Extractor()

    assert extractor.load(path) == HTML
    assert extractor.load(str(path)) == HTML


def test_load_returns_an_empty_string_when_missing(tmp_path: Path) -> None:
    extractor = Extractor()

    assert extractor.load(None) == ""
    assert extractor.load("") == ""
    assert extractor.load(tmp_path / "missing.html") == ""


def test_from_file_parses_a_stored_document(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    path.write_text(HTML, encoding="utf-8")

    extracted = Extractor().from_file(URL, path)

    assert extracted.title == "Example"
    assert extracted.links == ["/one", "https://example.com/two"]


def test_content_hash_is_deterministic() -> None:
    assert Extractor().content_hash(None) is None
    assert Extractor().content_hash("") is None


def test_content_hash_digest_matches_body(tmp_path: Path) -> None:
    import hashlib

    path = tmp_path / "page.html"
    body = b"<html>body</html>"
    path.write_bytes(body)

    assert Extractor().content_hash(path) == hashlib.sha256(body).hexdigest()


def test_content_hash_returns_none_when_missing(tmp_path: Path) -> None:
    assert Extractor().content_hash(tmp_path / "missing.html") is None
