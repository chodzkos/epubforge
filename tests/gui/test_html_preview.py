"""Testy podglądu XHTML: czysta funkcja inline_images + integracja w EditorTab."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from PySide6.QtGui import QTextCursor
from pytestqt.qtbot import QtBot

from epubforge.core import Tool
from epubforge.gui.tabs import editor_preview
from epubforge.gui.tabs.editor import EditorTab
from epubforge.gui.tabs.editor_preview import _PAGE_HTML
from epubforge.gui.widgets.html_preview import _PAPER_BG, inline_images

pytestmark = pytest.mark.gui

# 1x1 PNG.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f9b0000000049454e44ae426082"
)


# ── inline_images (czyste) ──────────────────────────────────────────────────--


def test_inline_images_embeds_small_image_as_data_uri() -> None:
    """Mały obrazek o względnym src trafia jako data: URI z bajtów."""
    out = inline_images('<html><body><img src="img/p.png"/></body></html>', lambda _s: _PNG)
    assert "data:image/png;base64," in out
    assert "img/p.png" not in out


def test_inline_images_oversized_becomes_placeholder() -> None:
    """Obraz > limitu jest zastępowany placeholderem z nazwą, nie base64."""
    big = b"Y" * (4 * 1024 * 1024)
    out = inline_images(
        '<html><body><img src="img/big.png"/></body></html>', lambda _s: big, max_bytes=3_000_000
    )
    assert "data:" not in out
    assert "big.png" in out


def test_inline_images_skips_external_and_missing() -> None:
    """Zewnętrzne (http) i nierozwiązane src zostają bez zmian."""
    external = inline_images(
        '<html><body><img src="http://x/y.png"/></body></html>', lambda _s: _PNG
    )
    assert "http://x/y.png" in external and "data:" not in external
    missing = inline_images('<html><body><img src="gone.png"/></body></html>', lambda _s: None)
    assert "gone.png" in missing and "data:" not in missing


# ── Integracja w EditorTab ──────────────────────────────────────────────────--


def _make_html_epub(path: Path) -> None:
    container = (
        b'<?xml version="1.0"?><container version="1.0" '
        b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        b'<rootfiles><rootfile full-path="OEBPS/content.opf" '
        b'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        b'<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" '
        b'version="3.0" unique-identifier="i">'
        b'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        b'<dc:identifier id="i">x</dc:identifier><dc:title>T</dc:title></metadata>'
        b'<manifest><item id="h" href="ch.xhtml" media-type="application/xhtml+xml"/>'
        b'<item id="img" href="img/p.png" media-type="image/png"/></manifest>'
        b'<spine><itemref idref="h"/></spine></package>'
    )
    chapter = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>R</title></head>'
        b'<body><h1>Rozdzial PODGLAD</h1><img src="img/p.png"/></body></html>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/ch.xhtml", chapter)
        zf.writestr("OEBPS/img/p.png", _PNG)


def _open_html(qtbot: QtBot, tmp_path: Path, **kwargs: object) -> EditorTab:
    book = tmp_path / "b.epub"
    _make_html_epub(book)
    tab = EditorTab(**kwargs)  # type: ignore[arg-type]
    qtbot.addWidget(tab)
    tab.open_epub(book)
    tab._select_path("OEBPS/ch.xhtml")
    return tab


def test_view_switch_visible_for_html(qtbot: QtBot, tmp_path: Path) -> None:
    """Dla HTML widoczny jest przełącznik Kod/Podgląd, domyślnie Kod."""
    tab = _open_html(qtbot, tmp_path)
    assert not tab.view_switch.isHidden()
    assert tab.code_view_button.isChecked() is True
    assert tab.stack.currentIndex() != _PAGE_HTML


def test_preview_toggle_renders_content(qtbot: QtBot, tmp_path: Path) -> None:
    """Przełączenie na Podgląd pokazuje stronę HTML z treścią rozdziału."""
    tab = _open_html(qtbot, tmp_path)
    tab.preview_view_button.setChecked(True)
    assert tab.stack.currentIndex() == _PAGE_HTML
    qtbot.waitUntil(lambda: "PODGLAD" in tab.html_preview.view.toPlainText(), timeout=2_000)


def test_preview_reflects_edits(qtbot: QtBot, tmp_path: Path) -> None:
    """Edycja kodu i przełączenie na Podgląd pokazuje niezapisaną zmianę."""
    tab = _open_html(qtbot, tmp_path)
    tab.edit_toggle.setChecked(True)
    cursor = tab.code_editor.editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.insertText(
        '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body>'
        "<p>NOWA TRESC EDYCJI</p></body></html>"
    )
    tab.preview_view_button.setChecked(True)
    qtbot.waitUntil(
        lambda: "NOWA TRESC EDYCJI" in tab.html_preview.view.toPlainText(), timeout=2_000
    )


def test_external_button_launches_with_current_epub(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Przyciski Sigil/Calibre wołają launch_tool z bieżącym plikiem EPUB."""
    calls: list[tuple[object, Path]] = []
    monkeypatch.setattr(
        editor_preview, "launch_tool", lambda tool, target: calls.append((tool, target))
    )
    tools = {"sigil": Tool("sigil", Path("/bin/sigil"), "", True)}
    tab = _open_html(qtbot, tmp_path, tools=tools)
    tab._launch_external_tool("sigil")
    assert calls == [(tools["sigil"], tab._epub_path)]


def test_preview_paper_is_theme_independent(qtbot: QtBot, tmp_path: Path) -> None:
    """Tło podglądu pozostaje białe niezależnie od motywu aplikacji."""
    from chodzkos_gui_kit.palette import DARK, LIGHT

    tab = _open_html(qtbot, tmp_path)
    tab.set_theme(DARK)
    assert _PAPER_BG in tab.html_preview.view.styleSheet()
    tab.set_theme(LIGHT)
    assert _PAPER_BG in tab.html_preview.view.styleSheet()
