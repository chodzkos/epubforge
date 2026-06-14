"""Testy GUI inspektora CSS (CssInspector + integracja w EditorTab)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from epubforge.gui.tabs.editor import EditorTab
from epubforge.gui.widgets.css_inspector import CssInspector

pytestmark = pytest.mark.gui

_CSS = "h1 { color: red }\np { font-size: 12pt; letter-spacing: 2px }\n"


def _make_css_epub(path: Path, css: str = _CSS) -> None:
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
        b'<manifest><item id="c" href="s.css" media-type="text/css"/>'
        b'<item id="h" href="a.xhtml" media-type="application/xhtml+xml"/></manifest>'
        b'<spine><itemref idref="h"/></spine></package>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/s.css", css.encode("utf-8"))
        zf.writestr("OEBPS/a.xhtml", b"<html><body><p>x</p></body></html>")


def _open_css(qtbot: QtBot, tmp_path: Path) -> EditorTab:
    book = tmp_path / "b.epub"
    _make_css_epub(book)
    tab = EditorTab()
    qtbot.addWidget(tab)
    tab.open_epub(book)
    tab.edit_toggle.setChecked(True)
    tab._select_path("OEBPS/s.css")
    return tab


def test_inspector_visible_for_css_and_loads_rule(qtbot: QtBot, tmp_path: Path) -> None:
    """Dla CSS panel jest aktywny i wybór reguły ładuje edytor reguły."""
    tab = _open_css(qtbot, tmp_path)
    assert tab.inspector_toggle.isEnabled()
    assert not tab.css_inspector.isHidden()
    insp = tab.css_inspector
    insp.tree.setCurrentItem(insp.tree.topLevelItem(0))
    assert insp.rule_editor.get_text().strip() == "h1 { color: red }"


def test_inspector_hidden_for_non_css(qtbot: QtBot, tmp_path: Path) -> None:
    """Dla pliku nie-CSS panel jest schowany i toggle nieaktywny."""
    tab = _open_css(qtbot, tmp_path)
    tab._select_path("OEBPS/a.xhtml")
    assert tab.css_inspector.isHidden()
    assert not tab.inspector_toggle.isEnabled()


def test_live_preview_updates_after_debounce(qtbot: QtBot, tmp_path: Path) -> None:
    """Edycja color: red → blue po debounce zmienia podgląd (Qt: blue → #0000ff)."""
    tab = _open_css(qtbot, tmp_path)
    insp = tab.css_inspector
    insp.tree.setCurrentItem(insp.tree.topLevelItem(0))
    insp.rule_editor.editor.setPlainText("h1 { color: blue }")
    qtbot.wait(400)  # przeskocz debounce 300 ms
    assert "#0000ff" in insp.preview.toHtml().lower()


def test_apply_writes_to_main_editor_and_undo_reverts(qtbot: QtBot, tmp_path: Path) -> None:
    """Zastosuj wpisuje zmianę do głównego edytora; undo cofa ją w całości."""
    tab = _open_css(qtbot, tmp_path)
    insp = tab.css_inspector
    insp.tree.setCurrentItem(insp.tree.topLevelItem(0))
    insp.rule_editor.editor.setPlainText("h1 { color: blue }")
    insp.apply_button.click()

    assert "color: blue" in tab.code_editor.get_text()
    qtbot.keyClick(tab.code_editor.editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert "color: red" in tab.code_editor.get_text()
    assert "color: blue" not in tab.code_editor.get_text()


def test_read_only_inspector_hides_apply(qtbot: QtBot) -> None:
    """Inspektor bez apply_replacement (np. podgląd presetu) chowa Zastosuj."""
    inspector = CssInspector(get_source=lambda: _CSS, apply_replacement=None)
    qtbot.addWidget(inspector)
    assert not inspector.apply_button.isVisibleTo(inspector)
    assert inspector.rule_editor.read_only is True
    assert inspector.tree.topLevelItemCount() == 2
