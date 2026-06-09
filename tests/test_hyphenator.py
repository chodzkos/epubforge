"""Testy dzielenia wyrazów w EPUB."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pyphen
import pytest

from epubforge.cli.main import main
from epubforge.core import Epub
from epubforge.fixers import HyphenationOptions, hyphenate
from epubforge.fixers.hyphenator import SOFT_HYPHEN


def _build_epub(tmp_path: Path, body: str, css: str | None = None) -> Path:
    """Tworzy minimalny EPUB z jednym XHTML i opcjonalnym arkuszem CSS."""
    epub_path = tmp_path / "book.epub"
    css_item = '<item id="style" href="styles/main.css" media-type="text/css"/>'
    css_link = '<link rel="stylesheet" type="text/css" href="../styles/main.css"/>'
    manifest_css = css_item if css is not None else ""
    head_css = css_link if css is not None else ""

    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
    content_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <manifest>
    <item id="chapter1" href="text/chapter1.xhtml" media-type="application/xhtml+xml"/>
    {manifest_css}
  </manifest>
  <spine>
    <itemref idref="chapter1"/>
  </spine>
</package>
"""
    chapter = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title>{head_css}</head>
  <body>{body}</body>
</html>
"""

    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", content_opf.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/text/chapter1.xhtml", chapter.encode(), zipfile.ZIP_DEFLATED)
        if css is not None:
            zf.writestr("OEBPS/styles/main.css", css.encode(), zipfile.ZIP_DEFLATED)
    return epub_path


def _read_text(epub: Epub) -> str:
    """Czyta XHTML z testowego EPUB-a."""
    return epub.read_file("OEBPS/text/chapter1.xhtml").decode()


def _expected_word(language: str, word: str) -> str:
    """Zwraca słowo podzielone przez Pyphen tak jak w kodzie produkcyjnym."""
    return pyphen.Pyphen(lang=language).inserted(word, hyphen=SOFT_HYPHEN)


def test_soft_hyphen_hyphenates_polish_text(tmp_path: Path) -> None:
    """Metoda soft-hyphen dzieli polskie słowa w tekście XHTML."""
    word = "konstantynopolitańczykowianeczka"
    epub_path = _build_epub(tmp_path, f"<p>{word}</p>")

    with Epub(epub_path) as epub:
        hyphenate(epub, HyphenationOptions(language="pl"))
        html = _read_text(epub)

    assert _expected_word("pl", word) in html
    assert SOFT_HYPHEN in html


def test_css_method_injects_rule_without_touching_text(tmp_path: Path) -> None:
    """Metoda css dopisuje regułę do arkusza, a tekst XHTML zostawia czysty."""
    word = "konstantynopolitańczykowianeczka"
    epub_path = _build_epub(tmp_path, f"<p>{word}</p>", css="p { color: black; }\n")

    with Epub(epub_path) as epub:
        hyphenate(epub, HyphenationOptions(method="css"))
        html = _read_text(epub)
        css = epub.read_file("OEBPS/styles/main.css").decode()

    assert "hyphens: auto" in css
    assert "-webkit-hyphens: auto" in css
    assert "hyphenate-limit-chars: 5 2 2" in css
    assert word in html
    assert SOFT_HYPHEN not in html


def test_soft_hyphen_skips_code_like_tags_and_headers(tmp_path: Path) -> None:
    """Tagi techniczne oraz h1-h3 są pomijane przy soft-hyphen."""
    word = "konstantynopolitańczykowianeczka"
    body = (
        f"<h1>{word}</h1>"
        f"<p><code>{word}</code><pre>{word}</pre><kbd>{word}</kbd>"
        f"<samp>{word}</samp><var>{word}</var><tt>{word}</tt>{word}</p>"
    )
    epub_path = _build_epub(tmp_path, body)

    with Epub(epub_path) as epub:
        hyphenate(epub, HyphenationOptions(language="pl", skip_headers=True))
        html = _read_text(epub)

    assert f"<h1>{word}</h1>" in html
    for tag in ("code", "pre", "kbd", "samp", "var", "tt"):
        assert f"<{tag}>{word}</{tag}>" in html
    assert _expected_word("pl", word) in html


def test_soft_hyphen_is_idempotent(tmp_path: Path) -> None:
    """Drugi przebieg nie dodaje kolejnych soft hyphenów."""
    word = "konstantynopolitańczykowianeczka"
    epub_path = _build_epub(tmp_path, f"<p>{word}</p>")

    with Epub(epub_path) as epub:
        options = HyphenationOptions(language="pl")
        hyphenate(epub, options)
        first = _read_text(epub)
        hyphenate(epub, options)
        second = _read_text(epub)

    assert first == second


@pytest.mark.parametrize(
    ("language", "word"),
    [
        ("en", "extraordinary"),
        ("de", "Donaudampfschifffahrt"),
    ],
)
def test_soft_hyphen_supports_other_languages(
    tmp_path: Path,
    language: str,
    word: str,
) -> None:
    """Pyphen language option działa dla języka angielskiego i niemieckiego."""
    epub_path = _build_epub(tmp_path, f"<p>{word}</p>")

    with Epub(epub_path) as epub:
        hyphenate(epub, HyphenationOptions(language=language))
        html = _read_text(epub)

    assert _expected_word(language, word) in html


def test_cli_hyphenate_saves_epub(tmp_path: Path, capsys) -> None:
    """Subkomenda hyphenate modyfikuje i zapisuje wskazany EPUB."""
    epub_path = _build_epub(tmp_path, "<p>tekst próbny</p>", css="")

    exit_code = main(["hyphenate", str(epub_path), "--method", "css"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"Zaktualizowano EPUB: {epub_path}" in captured.out
    with Epub(epub_path) as epub:
        css = epub.read_file("OEBPS/styles/main.css").decode()
    assert "hyphens: auto" in css
