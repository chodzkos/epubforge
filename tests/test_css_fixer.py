"""Testy normalizacji CSS w EPUB."""

from __future__ import annotations

import zipfile
from pathlib import Path

from epubforge.cli.main import main
from epubforge.core import Epub
from epubforge.fixers import CssFixOptions, fix_css
from epubforge.fixers.css_fixer import (
    _inject_book_margin,
    _inject_reset,
    _remove_colors,
    _replace_justify,
    _skip_hyphenation_headers,
)


def _build_epub(tmp_path: Path, css: str, include_font: bool = False) -> Path:
    """Tworzy minimalny EPUB z jednym arkuszem CSS i opcjonalnym fontem."""
    epub_path = tmp_path / "book.epub"
    font_item = (
        '<item id="font" href="fonts/book.woff2" media-type="font/woff2"/>' if include_font else ""
    )
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
    <item id="style" href="styles/main.css" media-type="text/css"/>
    {font_item}
  </manifest>
  <spine>
    <itemref idref="chapter1"/>
  </spine>
</package>
"""
    chapter = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><link rel="stylesheet" type="text/css" href="../styles/main.css"/></head>
  <body><p>Test</p></body>
</html>
"""

    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", content_opf.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/text/chapter1.xhtml", chapter.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/styles/main.css", css.encode(), zipfile.ZIP_DEFLATED)
        if include_font:
            zf.writestr("OEBPS/fonts/book.woff2", b"font-data", zipfile.ZIP_DEFLATED)
    return epub_path


def _read_css(epub: Epub) -> str:
    """Czyta CSS z testowego EPUB-a."""
    return epub.read_file("OEBPS/styles/main.css").decode()


def _compact(css: str) -> str:
    """Usuwa whitespace do stabilnych porównań serializacji tinycss2."""
    return "".join(css.split())


def test_remove_colors_removes_color_background_properties() -> None:
    """remove_colors usuwa tylko celowane deklaracje kolorów i tła."""
    css = "p { color: red; background: white; background-color: #fff; margin: 1em; }"

    fixed = _remove_colors(css)

    assert "color:" not in fixed
    assert "background:" not in fixed
    assert "background-color:" not in fixed
    assert "margin:1em" in _compact(fixed)


def test_remove_fonts_removes_css_and_physical_font_files(tmp_path: Path) -> None:
    """remove_fonts usuwa @font-face, font-family, pliki fontów i wpis OPF."""
    css = (
        "@font-face { font-family: Book; src: url('../fonts/book.woff2'); }"
        "body { font-family: Book, serif; margin: 1em; }"
    )
    epub_path = _build_epub(tmp_path, css, include_font=True)

    with Epub(epub_path) as epub:
        fix_css(
            epub,
            CssFixOptions(
                remove_fonts=True,
                inject_reset=False,
                skip_hyphenation_headers=False,
            ),
        )
        epub.save()

    with Epub(epub_path) as epub:
        fixed = _read_css(epub)
        opf = epub.read_file(epub.opf_path).decode()
        files = epub.list_files()

    assert "@font-face" not in fixed
    assert "font-family" not in fixed
    assert "margin:1em" in _compact(fixed)
    assert "OEBPS/fonts/book.woff2" not in files
    assert "book.woff2" not in opf


def test_inject_reset_adds_minimal_reset() -> None:
    """inject_reset dodaje regułę z margin/padding zero."""
    fixed = _inject_reset("p { margin: 1em; }")

    assert "html, body" in fixed
    compact = _compact(fixed)
    assert "margin:0" in compact
    assert "padding:0" in compact
    assert fixed == _inject_reset(fixed)


def test_replace_justify_changes_only_text_align_justify() -> None:
    """replace_justify zamienia justify na left."""
    fixed = _replace_justify("p { text-align: justify; margin: 1em; }")

    assert "text-align:left" in fixed
    assert "justify" not in fixed
    assert "margin:1em" in _compact(fixed)


def test_inject_book_margin_adds_page_margin() -> None:
    """book margin dodaje @page margin w pikselach."""
    fixed = _inject_book_margin("p { margin: 1em; }", 12)

    assert "@page" in fixed
    assert "margin:12px" in _compact(fixed)


def test_inject_book_margin_updates_existing_page_margin() -> None:
    """book margin aktualizuje istniejący @page zamiast mnożyć deklaracje margin."""
    fixed = _inject_book_margin("@page { margin: 5px; size: A5; }", 20)

    compact = _compact(fixed)
    assert "margin:20px" in compact
    assert "size:A5" in compact
    assert "margin:5px" not in compact


def test_skip_hyphenation_headers_adds_header_rule() -> None:
    """skip_hyphenation_headers dodaje regułę h1-h3."""
    fixed = _skip_hyphenation_headers("p { margin: 1em; }")

    assert "h1, h2, h3" in fixed
    assert "hyphens:none" in _compact(fixed)
    assert fixed == _skip_hyphenation_headers(fixed)


def test_combined_options_apply_together(tmp_path: Path) -> None:
    """Kombinacja opcji działa na jednym arkuszu."""
    css = "p { color: red; text-align: justify; background: white; }"
    epub_path = _build_epub(tmp_path, css)

    with Epub(epub_path) as epub:
        fix_css(
            epub,
            CssFixOptions(
                remove_colors=True,
                replace_justify="left",
                inject_book_margin_px=18,
            ),
        )
        fixed = _read_css(epub)

    assert "color:" not in fixed
    assert "background:" not in fixed
    assert "text-align:left" in fixed
    compact = _compact(fixed)
    assert "margin:18px" in compact
    assert "hyphens:none" in compact
    assert "padding:0" in compact


def test_modern_css3_is_not_damaged() -> None:
    """Custom properties, @supports i calc() przechodzą przez fixer bez uszkodzeń."""
    css = (
        ":root { --gap: calc(1rem + 2px); --main-color: #333; }"
        "@supports (display: grid) { .grid { display: grid; gap: var(--gap); } }"
        "p { margin: calc(var(--gap) * 2); text-align: justify; }"
    )

    fixed = _replace_justify(_remove_colors(css))

    compact = _compact(fixed)
    assert "--gap:calc(1rem+2px)" in compact
    assert "--main-color:#333" in compact
    assert "@supports (display: grid)" in fixed
    assert "gap: var(--gap)" in fixed
    assert "margin:calc(var(--gap)*2)" in compact
    assert "text-align:left" in fixed


def test_cli_fix_saves_epub(tmp_path: Path, capsys) -> None:
    """Subkomenda fix zapisuje zmieniony CSS w EPUB-ie."""
    epub_path = _build_epub(tmp_path, "p { color: red; text-align: justify; }")

    exit_code = main(["fix", str(epub_path), "--remove-colors", "--replace-justify"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"Zaktualizowano EPUB: {epub_path}" in captured.out
    with Epub(epub_path) as epub:
        fixed = _read_css(epub)
    assert "color:" not in fixed
    assert "text-align:left" in fixed
