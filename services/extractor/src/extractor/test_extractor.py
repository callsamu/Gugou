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


def test_extract_prefers_article_and_ignores_chrome() -> None:
    html = """
    <html>
      <head><title>Page title</title></head>
      <body>
        <header><h1>Site header</h1><nav><a href="/nav">nav</a></nav></header>
        <main>
          <p>Outside article</p>
          <article>
            <header><h1>Article header</h1></header>
            <h2>Article title</h2>
            <p>First <b>paragraph</b>.</p>
            <aside><p>Aside noise</p></aside>
            <a href="/article">article link</a>
            <footer><p>Article footer</p></footer>
          </article>
        </main>
        <footer><p>Site footer</p></footer>
      </body>
    </html>
    """

    extracted = Extractor().extract(URL, html)

    assert extracted.title == "Page title"
    assert extracted.text == "Article title\nFirst paragraph."
    assert extracted.links == ["/article"]


def test_extract_falls_back_to_main() -> None:
    html = """
    <body>
      <header><p>Header</p></header>
      <main><h1>Main heading</h1><p>Main body</p><aside><p>Aside</p></aside></main>
      <footer><p>Footer</p></footer>
    </body>
    """

    extracted = Extractor().extract(URL, html)

    assert extracted.text == "Main heading\nMain body"


def test_extract_ignores_chrome_without_article_or_main() -> None:
    html = """
    <body>
      <header><h1>Header</h1></header>
      <nav><p>Nav</p></nav>
      <h1>Content</h1>
      <p>Body</p>
      <aside><p>Aside</p></aside>
      <footer><p>Footer</p></footer>
    </body>
    """

    extracted = Extractor().extract(URL, html)

    assert extracted.text == "Content\nBody"


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
