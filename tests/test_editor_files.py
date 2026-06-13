"""Testy czystej logiki edytora (klasyfikacja, profil, dekodowanie, pozycje, spany)."""

from __future__ import annotations

import pytest

from epubforge.gui import editor_files as ef
from epubforge.gui.widgets.syntax_highlight import css_spans, xml_spans


@pytest.mark.parametrize(
    ("path", "media_type", "expected"),
    [
        ("OEBPS/text/ch1.xhtml", "application/xhtml+xml", ef.GROUP_TEXT),
        ("OEBPS/content.opf", "application/oebps-package+xml", ef.GROUP_TEXT),
        ("toc.ncx", "application/x-dtbncx+xml", ef.GROUP_TEXT),
        ("styles/main.css", "text/css", ef.GROUP_STYLE),
        ("images/cover.png", "image/png", ef.GROUP_IMAGE),
        ("images/p.jpg", None, ef.GROUP_IMAGE),
        ("fonts/serif.ttf", None, ef.GROUP_FONT),
        ("fonts/x.woff2", "font/woff2", ef.GROUP_FONT),
        ("art/draw.svg", "image/svg+xml", ef.GROUP_TEXT),  # SVG edytowalny jako XML
        ("data/book.smil", "application/smil+xml", ef.GROUP_OTHER),
    ],
)
def test_classify(path: str, media_type: str | None, expected: str) -> None:
    """Klasyfikacja po media-type, z fallbackiem na rozszerzenie."""
    assert ef.classify(path, media_type) == expected


def test_profile_for() -> None:
    """Profil podświetlania: css dla CSS, xml dla XHTML/OPF/NCX/SVG, None dla reszty."""
    assert ef.profile_for("a.css", "text/css") == ef.PROFILE_CSS
    assert ef.profile_for("a.xhtml", "application/xhtml+xml") == ef.PROFILE_XML
    assert ef.profile_for("a.svg", None) == ef.PROFILE_XML
    assert ef.profile_for("a.png", "image/png") is None


def test_decode_text_replacement() -> None:
    """Poprawny UTF-8 bez podmian; bajty nie-UTF-8 → znak zastępczy i flaga."""
    text, replaced = ef.decode_text("Zażółć gęślą".encode())
    assert text == "Zażółć gęślą"
    assert replaced is False
    bad_text, bad_replaced = ef.decode_text(b"abc\xff\xfe")
    assert bad_replaced is True
    assert "�" in bad_text


def test_offset_line_col_roundtrip() -> None:
    """offset↔(linia,kolumna) — 1-based, spójne w obie strony."""
    text = "abc\ndef\nghi"
    assert ef.offset_to_line_col(text, 0) == (1, 1)
    assert ef.offset_to_line_col(text, 5) == (2, 2)
    assert ef.offset_to_line_col(text, len(text)) == (3, 4)
    assert ef.line_col_to_offset(text, 2, 2) == 5
    assert ef.line_col_to_offset(text, 3, 1) == 8


def test_xml_spans_kinds() -> None:
    """xml_spans rozpoznaje tag, atrybut, wartość i encję."""
    kinds = {kind for _s, _l, kind in xml_spans('<p class="a">&amp;</p>')}
    assert {"tag", "attribute", "value", "entity"} <= kinds


def test_css_spans_kinds() -> None:
    """css_spans rozpoznaje selektor, właściwość, wartość, @-regułę i !important."""
    kinds = {kind for _s, _l, kind in css_spans("@media{body{color:red !important;}}")}
    assert "atrule" in kinds
    assert "property" in kinds
    assert "important" in kinds
