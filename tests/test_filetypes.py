"""Testy czystej klasyfikacji typów plików i helperów tekstowych w ``core``.

Moduły ``core.filetypes`` i ``core.textutil`` nie zależą od Qt — te testy biegają
także w bazowej instalacji (bez extra ``gui``). Sprawdzamy dodatkowo, że warstwa
GUI (:mod:`epubforge.gui.editor_files`) re-eksportuje dokładnie te same obiekty.
"""

from __future__ import annotations

import pytest

from epubforge.core import filetypes as ft
from epubforge.core import textutil as tu


@pytest.mark.parametrize(
    ("path", "media_type", "expected"),
    [
        ("OEBPS/text/ch1.xhtml", "application/xhtml+xml", ft.GROUP_TEXT),
        ("OEBPS/content.opf", "application/oebps-package+xml", ft.GROUP_TEXT),
        ("toc.ncx", "application/x-dtbncx+xml", ft.GROUP_TEXT),
        ("styles/main.css", "text/css", ft.GROUP_STYLE),
        ("images/cover.png", "image/png", ft.GROUP_IMAGE),
        ("images/p.jpg", None, ft.GROUP_IMAGE),
        ("fonts/serif.ttf", None, ft.GROUP_FONT),
        ("fonts/x.woff2", "font/woff2", ft.GROUP_FONT),
        ("art/draw.svg", "image/svg+xml", ft.GROUP_TEXT),  # SVG edytowalny jako XML
        ("data/book.smil", "application/smil+xml", ft.GROUP_OTHER),
    ],
)
def test_classify(path: str, media_type: str | None, expected: str) -> None:
    """Klasyfikacja po media-type, z fallbackiem na rozszerzenie."""
    assert ft.classify(path, media_type) == expected


def test_profile_for() -> None:
    """Profil podświetlania: css dla CSS, xml dla XHTML/OPF/NCX/SVG, None dla reszty."""
    assert ft.profile_for("a.css", "text/css") == ft.PROFILE_CSS
    assert ft.profile_for("a.xhtml", "application/xhtml+xml") == ft.PROFILE_XML
    assert ft.profile_for("a.svg", None) == ft.PROFILE_XML
    assert ft.profile_for("a.png", "image/png") is None


def test_is_editable_and_predicates() -> None:
    """``is_editable``/``is_image``/``is_html`` — spójne z profilem i grupą."""
    assert ft.is_editable("a.xhtml", "application/xhtml+xml") is True
    assert ft.is_editable("a.png", "image/png") is False
    assert ft.is_image("cover.png", "image/png") is True
    assert ft.is_html("ch1.xhtml", None) is True
    assert ft.is_html("toc.ncx", "application/x-dtbncx+xml") is False


def test_decode_text_replacement() -> None:
    """Poprawny UTF-8 bez podmian; bajty nie-UTF-8 → znak zastępczy i flaga."""
    text, replaced = tu.decode_text("Zażółć gęślą".encode())
    assert text == "Zażółć gęślą"
    assert replaced is False
    bad_text, bad_replaced = tu.decode_text(b"abc\xff\xfe")
    assert bad_replaced is True
    assert "�" in bad_text


def test_offset_line_col_roundtrip() -> None:
    """offset↔(linia,kolumna) — 1-based, spójne w obie strony."""
    text = "abc\ndef\nghi"
    assert tu.offset_to_line_col(text, 0) == (1, 1)
    assert tu.offset_to_line_col(text, 5) == (2, 2)
    assert tu.offset_to_line_col(text, len(text)) == (3, 4)
    assert tu.line_col_to_offset(text, 2, 2) == 5
    assert tu.line_col_to_offset(text, 3, 1) == 8


def test_gui_editor_files_reexports_core() -> None:
    """Shim ``gui.editor_files`` re-eksportuje te same obiekty co ``core`` (bez Qt)."""
    from epubforge.gui import editor_files as ef

    assert ef.classify is ft.classify
    assert ef.is_editable is ft.is_editable
    assert ef.profile_for is ft.profile_for
    assert ef.decode_text is tu.decode_text
    assert ef.resolve_internal_path is tu.resolve_internal_path
    assert ef.GROUP_ORDER == ft.GROUP_ORDER
