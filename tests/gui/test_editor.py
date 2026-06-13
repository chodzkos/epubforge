"""Testy GUI edytora wewnętrznego EPUB (CodeEditor + EditorTab)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from PySide6.QtGui import QTextCursor, QTextDocument
from pytestqt.qtbot import QtBot

from epubforge.core import Epub
from epubforge.gui.tabs.editor import EditorTab
from epubforge.gui.widgets.code_editor import CodeEditor
from epubforge.gui.widgets.syntax_highlight import XmlHighlighter

pytestmark = pytest.mark.gui

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.epub"
_CHAPTER = "OEBPS/text/chapter1.xhtml"


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "book.epub"
    target.write_bytes(_FIXTURE.read_bytes())
    return target


# ── CodeEditor ─────────────────────────────────────────────────────────────--


def test_load_get_text_roundtrip_polish(qtbot: QtBot) -> None:
    """load/get_text zachowuje polskie znaki."""
    editor = CodeEditor()
    qtbot.addWidget(editor)
    text = "<p>Zażółć gęślą jaźń</p>\n<p>ąćęłńóśźż</p>"
    editor.load(text, "xml")
    assert editor.get_text() == text
    assert editor.is_modified() is False  # load nie liczy się jako modyfikacja


def test_goto_line_moves_cursor(qtbot: QtBot) -> None:
    """goto_line ustawia kursor w żądanej linii."""
    editor = CodeEditor()
    qtbot.addWidget(editor)
    editor.load("l1\nl2\nl3\nl4", None)
    editor.goto_line(3)
    assert editor.editor.textCursor().blockNumber() == 2


def test_read_only_blocks_typing(qtbot: QtBot) -> None:
    """W trybie read_only wpisywanie tekstu jest blokowane."""
    editor = CodeEditor()
    qtbot.addWidget(editor)
    editor.load("abc", None)
    editor.read_only = True
    editor.editor.setFocus()
    qtbot.keyClicks(editor.editor, "XYZ")
    assert editor.get_text() == "abc"


def test_search_counts_matches(qtbot: QtBot) -> None:
    """Wyszukiwarka liczy trafienia i podświetla je."""
    editor = CodeEditor()
    qtbot.addWidget(editor)
    editor.load("ala ma kota, ala ma psa, ALA", None)
    editor.show_search()
    editor.search_field.setText("ala")
    assert editor.match_count() == 3  # bez rozróżniania wielkości liter
    assert editor.search_count.text() == "1/3"


def test_highlighter_assigns_formats(qtbot: QtBot) -> None:
    """XmlHighlighter nadaje formaty znakom w bloku."""
    document = QTextDocument()
    document.setPlainText('<p class="x">hi</p>')
    highlighter = XmlHighlighter(document)
    qtbot.addWidget(CodeEditor())  # zapewnia żywą pętlę zdarzeń
    highlighter.rehighlight()
    formats = document.findBlockByNumber(0).layout().formats()
    assert formats  # highlighter nałożył co najmniej jeden format


# ── EditorTab ────────────────────────────────────────────────────────────────


def test_open_epub_builds_tree(qtbot: QtBot) -> None:
    """Otwarcie sample.epub buduje drzewo z grupami i plikami."""
    tab = EditorTab()
    qtbot.addWidget(tab)
    assert tab.open_epub(_FIXTURE) is True
    assert tab.tree.topLevelItemCount() >= 1
    group = tab.tree.topLevelItem(0)
    assert group.childCount() >= 1


def test_edit_save_reopen_flow(qtbot: QtBot, tmp_path: Path) -> None:
    """Edycja XHTML → Ctrl+S → Zapisz EPUB → ponowne otwarcie pokazuje zmianę."""
    book = _copy_fixture(tmp_path)
    tab = EditorTab()
    qtbot.addWidget(tab)
    tab.open_epub(book)
    tab.edit_toggle.setChecked(True)
    tab._select_path(_CHAPTER)

    new_text = tab.code_editor.get_text().replace("Tekst próbny.", "ZMIANA TESTOWA.")
    # Edycja przez kursor (jak realny użytkownik) — oznacza dokument jako zmodyfikowany;
    # setPlainText to ścieżka „load" i NIE ustawia flagi modified.
    cursor = tab.code_editor.editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.insertText(new_text)
    assert tab.code_editor.is_modified() is True
    assert tab._save_current() is True  # commit do bufora EPUB
    tab._save_epub()  # zapis na dysk

    with Epub(book) as epub:
        saved = epub.read_file(_CHAPTER).decode("utf-8")
    assert "ZMIANA TESTOWA." in saved


def test_non_utf8_file_is_read_only(qtbot: QtBot, tmp_path: Path) -> None:
    """Plik z bajtami nie-UTF-8 wymusza tryb tylko do odczytu."""
    book = tmp_path / "bad.epub"
    container = (
        b'<?xml version="1.0"?><container version="1.0" '
        b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        b'<rootfiles><rootfile full-path="OEBPS/content.opf" '
        b'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="i">'
        b'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        b'<dc:identifier id="i">x</dc:identifier><dc:title>T</dc:title></metadata>'
        b'<manifest><item id="c" href="text/ch.xhtml" media-type="application/xhtml+xml"/>'
        b'</manifest><spine><itemref idref="c"/></spine></package>'
    )
    with zipfile.ZipFile(book, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/text/ch.xhtml", b"<html><body>\xff\xfe bad</body></html>")

    tab = EditorTab()
    qtbot.addWidget(tab)
    tab.open_epub(book)
    tab.edit_toggle.setChecked(True)
    tab._select_path("OEBPS/text/ch.xhtml")
    assert tab.code_editor.read_only is True
    assert tab.info_bar.text()  # pasek informacyjny niesie ostrzeżenie


def test_open_external_selects_file_and_line(qtbot: QtBot) -> None:
    """open_external (kontrakt open_in_editor) zaznacza plik i ustawia linię."""
    tab = EditorTab()
    qtbot.addWidget(tab)
    tab.open_external(_FIXTURE, _CHAPTER, line=3)
    assert tab._current == _CHAPTER
    assert tab.code_editor.editor.textCursor().blockNumber() == 2  # linia 3 → blok 2


def test_image_file_shows_preview_page(qtbot: QtBot, tmp_path: Path) -> None:
    """Plik obrazu przełącza prawy panel na podgląd obrazu."""
    # 1x1 PNG
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6360000002000154a24f9b0000000049454e44ae426082"
    )
    book = tmp_path / "img.epub"
    container = (
        b'<?xml version="1.0"?><container version="1.0" '
        b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        b'<rootfiles><rootfile full-path="OEBPS/content.opf" '
        b'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="i">'
        b'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        b'<dc:identifier id="i">x</dc:identifier><dc:title>T</dc:title></metadata>'
        b'<manifest><item id="img" href="img/p.png" media-type="image/png"/></manifest>'
        b"<spine/></package>"
    )
    with zipfile.ZipFile(book, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/img/p.png", png)

    tab = EditorTab()
    qtbot.addWidget(tab)
    tab.open_epub(book)
    tab._select_path("OEBPS/img/p.png")
    assert tab.stack.currentIndex() == 1  # strona podglądu obrazu
