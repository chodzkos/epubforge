"""Testy GUI edytora wewnętrznego EPUB (CodeEditor + EditorTab)."""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QAbstractButton, QHeaderView, QMessageBox
from pytestqt.qtbot import QtBot

from epubforge.core import Epub, Tool
from epubforge.gui.tabs import editor as editor_module
from epubforge.gui.tabs import editor_preview
from epubforge.gui.tabs.editor import EditorTab
from epubforge.gui.tabs.editor_preview import _PAGE_INFO
from epubforge.gui.widgets.code_editor import CodeEditor
from epubforge.gui.widgets.syntax_highlight import XmlHighlighter

pytestmark = pytest.mark.gui

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.epub"
_CHAPTER = "OEBPS/text/chapter1.xhtml"


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "book.epub"
    target.write_bytes(_FIXTURE.read_bytes())
    return target


def _handoff_tools() -> dict[str, Tool]:
    return {
        "sigil": Tool("sigil", Path("/tools/sigil"), "", True),
        "calibre_editor": Tool("calibre_editor", Path("/tools/ebook-edit"), "", True),
    }


def _make_single_resource_epub(path: Path, internal: str, media_type: str, payload: bytes) -> Path:
    """Buduje mały EPUB z jednym zasobem testowym zapisanym bez kompresji."""
    container = (
        b'<?xml version="1.0"?><container version="1.0" '
        b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        b'<rootfiles><rootfile full-path="OEBPS/content.opf" '
        b'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    href = internal.removeprefix("OEBPS/")
    opf = (
        b'<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" '
        b'version="3.0"><metadata/><manifest><item id="r" href="'
        + href.encode()
        + b'" media-type="'
        + media_type.encode()
        + b'"/></manifest><spine/></package>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container, zipfile.ZIP_STORED)
        archive.writestr("OEBPS/content.opf", opf, zipfile.ZIP_STORED)
        archive.writestr(internal, payload, zipfile.ZIP_STORED)
    return path


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


def test_top_toolbar_handoff_tracks_open_epub(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Górne przyciski otwierają cały EPUB i wyłączają się po jego zamknięciu."""
    tools = _handoff_tools()
    calls: list[tuple[Tool | None, Path]] = []
    monkeypatch.setattr(
        editor_preview, "launch_tool", lambda tool, target: calls.append((tool, target))
    )
    tab = EditorTab(tools=tools)
    qtbot.addWidget(tab)

    assert set(tab.external_tool_buttons) == {"sigil", "calibre_editor"}
    assert all(not button.isEnabled() for button in tab.external_tool_buttons.values())
    assert tab.open_epub(_FIXTURE)
    assert all(button.isEnabled() for button in tab.external_tool_buttons.values())

    tab.external_tool_buttons["sigil"].click()
    tab.external_tool_buttons["calibre_editor"].click()
    assert calls == [(tools["sigil"], _FIXTURE), (tools["calibre_editor"], _FIXTURE)]
    assert "zapisaną" in tab.external_tool_buttons["sigil"].toolTip()

    tab._close_epub()
    assert all(not button.isEnabled() for button in tab.external_tool_buttons.values())


def test_top_toolbar_handoff_missing_tool_has_explanation(qtbot: QtBot) -> None:
    """Niewykryte narzędzia pozostają nieaktywne z jednoznacznym tooltipem."""
    tab = EditorTab(tools={"sigil": Tool("sigil", None, "", False)})
    qtbot.addWidget(tab)
    tab.open_epub(_FIXTURE)

    assert not tab.external_tool_buttons["sigil"].isEnabled()
    assert tab.external_tool_buttons["sigil"].toolTip() == "Nie wykryto Sigil"
    assert not tab.external_tool_buttons["calibre_editor"].isEnabled()
    assert "Calibre Editor" in tab.external_tool_buttons["calibre_editor"].toolTip()


def test_file_tree_keeps_full_names_and_scrolls_immediately(qtbot: QtBot) -> None:
    """Kolumna nie rozciąga się do viewportu, więc scroll obejmuje całą długą nazwę."""
    tab = EditorTab()
    qtbot.addWidget(tab)
    tab.open_epub(_FIXTURE)
    item = next(tab._file_items())
    internal = str(item.data(0, Qt.ItemDataRole.UserRole))
    item.setText(0, "bardzo-dluga-nazwa-pliku-" * 12 + ".xhtml")
    tab.tree.resizeColumnToContents(0)
    tab.resize(820, 560)
    tab.show()
    qtbot.waitExposed(tab)

    assert item.toolTip(0) == internal
    assert tab.tree.textElideMode() == Qt.TextElideMode.ElideNone
    assert tab.tree.header().stretchLastSection() is False
    assert tab.tree.header().sectionResizeMode(0) == QHeaderView.ResizeMode.ResizeToContents
    assert tab.tree.columnWidth(0) > tab.tree.viewport().width()
    assert tab.tree.horizontalScrollBar().maximum() > 0


def test_editor_splitters_preserve_readable_panels(qtbot: QtBot) -> None:
    """Wszystkie poziome podziały mają uchwyty i blokadę zwijania paneli do zera."""
    tab = EditorTab()
    qtbot.addWidget(tab)
    for splitter in (tab.main_splitter, tab.content_splitter, tab.preview_split):
        assert splitter.childrenCollapsible() is False
        assert splitter.handleWidth() >= 8
    assert tab.tree.minimumWidth() >= 180
    assert tab.stack.minimumWidth() >= 300
    assert tab.css_inspector.minimumWidth() >= 360


def test_reset_layout_requires_confirmation_and_keeps_content(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reset zamyka panele dopiero po „Tak” i nie zmienia kodu dokumentu."""
    tab = EditorTab()
    qtbot.addWidget(tab)
    tab.open_epub(_FIXTURE)
    tab._select_path(_CHAPTER)
    original = tab.code_editor.get_text()
    tab.split_view_button.setChecked(True)
    tab.search_panel.setVisible(True)
    tab.book_preview.reader_settings_button.setChecked(True)
    tab.book_preview.diagnostics_button.setChecked(True)

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    tab.reset_layout_button.click()
    assert tab.split_view_button.isChecked()

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    tab.reset_layout_button.click()
    assert not tab.split_view_button.isChecked()
    assert not tab.inspector_toggle.isChecked()
    assert tab.search_panel.isHidden()
    assert not tab.book_preview.reader_settings_button.isChecked()
    assert not tab.book_preview.diagnostics_button.isChecked()
    assert tab.code_editor.get_text() == original


def test_editor_buttons_have_tooltips(qtbot: QtBot) -> None:
    """Audyt gui-kit: każda akcja przyciskowa edytora ma pełną podpowiedź."""
    tab = EditorTab()
    qtbot.addWidget(tab)
    missing = [
        button.text() for button in tab.findChildren(QAbstractButton) if not button.toolTip()
    ]
    assert missing == []


def test_edit_save_reopen_flow(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edycja XHTML → Ctrl+S → Zapisz EPUB → ponowne otwarcie pokazuje zmianę."""
    save_errors: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda _parent, _title, message: save_errors.append(message),
    )
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
    assert save_errors == []

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


def test_edit_mode_indicator_toggles(qtbot: QtBot, tmp_path: Path) -> None:
    """Przełącznik zmienia read-only, etykietę statusu i obwódkę edytora (akcent)."""
    from chodzkos_gui_kit.qt.theme import current_palette as current_theme

    accent = current_theme().accent
    book = _copy_fixture(tmp_path)
    tab = EditorTab()
    qtbot.addWidget(tab)
    tab.open_epub(book)
    tab._select_path(_CHAPTER)

    # Start: tryb podglądu — read-only, brak akcentu w obwódce, status fg2.
    assert tab.code_editor.read_only is True
    assert "Edycja" not in tab.mode_label.text()
    assert accent not in tab.code_editor.editor.styleSheet()

    # Włączenie edycji — edytor edytowalny, akcent w obwódce, etykieta „● Edycja".
    tab.edit_toggle.setChecked(True)
    assert tab.code_editor.read_only is False
    assert "Edycja" in tab.mode_label.text()
    assert accent in tab.code_editor.editor.styleSheet()
    assert "edycja" in tab.edit_toggle.text().lower()

    # Powrót do podglądu — akcent znika.
    tab.edit_toggle.setChecked(False)
    assert tab.code_editor.read_only is True
    assert accent not in tab.code_editor.editor.styleSheet()


def test_non_utf8_has_no_accent_frame_despite_edit_mode(qtbot: QtBot, tmp_path: Path) -> None:
    """Plik nie-UTF-8 zostaje read-only i bez akcentu mimo włączonego trybu edycji."""
    from chodzkos_gui_kit.qt.theme import current_palette as current_theme

    accent = current_theme().accent
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
    tab.edit_toggle.setChecked(True)  # tryb edycji włączony per sesja
    tab._select_path("OEBPS/text/ch.xhtml")
    assert tab.code_editor.read_only is True  # wymuszony read-only
    assert accent not in tab.code_editor.editor.styleSheet()  # brak akcentu


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


def test_editor_rejects_limit_plus_one_before_materialization(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tekst limit+1 pokazuje informację bez read/decode/QTextDocument i bez dirty."""
    limit = 64
    internal = "OEBPS/text/large.xhtml"
    book = _make_single_resource_epub(
        tmp_path / "large-text.epub", internal, "application/xhtml+xml", b"x" * (limit + 1)
    )
    monkeypatch.setattr(editor_module, "MAX_EDITOR_TEXT_BYTES", limit)
    tab = EditorTab()
    qtbot.addWidget(tab)
    assert tab.open_epub(book)
    assert tab._epub is not None
    original_read = tab._epub.read_file

    def guarded_read(path: str) -> bytes:
        if path == internal:
            pytest.fail("oversized tekst nie może wywołać read_file")
        return original_read(path)

    monkeypatch.setattr(tab._epub, "read_file", guarded_read)
    tab._show_file(internal)

    assert tab.stack.currentIndex() == _PAGE_INFO
    assert "zbyt duży" in tab.info_panel.text().lower()
    assert internal not in tab._dirty
    assert tab.code_editor.get_text() == ""


@pytest.mark.parametrize("size", [63, 64])
def test_editor_opens_limit_minus_one_and_exact_limit(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, size: int
) -> None:
    """Tekst limit-1 oraz dokładnie limit przechodzą normalną ścieżkę edytora."""
    internal = "OEBPS/text/allowed.xhtml"
    book = _make_single_resource_epub(
        tmp_path / f"allowed-{size}.epub", internal, "application/xhtml+xml", b"x" * size
    )
    monkeypatch.setattr(editor_module, "MAX_EDITOR_TEXT_BYTES", 64)
    tab = EditorTab()
    qtbot.addWidget(tab)
    assert tab.open_epub(book)

    tab._show_file(internal)

    assert tab.code_editor.get_text() == "x" * size
    assert tab.stack.currentIndex() == 0


def test_binary_100_mib_uses_metadata_without_materialization(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kliknięcie dużego fontu pokazuje nazwę/typ/rozmiar bez read_file."""
    internal = "OEBPS/fonts/huge.ttf"
    tab = EditorTab()
    qtbot.addWidget(tab)
    assert tab.open_epub(_FIXTURE)
    assert tab._epub is not None
    tab._media_types[internal] = "font/ttf"
    monkeypatch.setattr(tab._epub, "get_file_size", lambda _path: 100 * 1024 * 1024)
    monkeypatch.setattr(
        tab._epub,
        "read_file",
        lambda _path: pytest.fail("panel metadanych binarium nie może czytać treści"),
    )

    tab._show_file(internal)

    assert tab.stack.currentIndex() == _PAGE_INFO
    assert internal in tab.info_panel.text()
    assert "104857600" in tab.info_panel.text()


def test_skipped_oversized_member_is_preserved_after_edit_and_save(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Odrzucony obraz pozostaje bajtowo nietknięty po zapisie małego rozdziału."""
    book = _copy_fixture(tmp_path)
    large_path = "OEBPS/images/large.png"
    large_payload = (b"unchanged-large-resource-" * 45_000)[: 1024 * 1024]
    with zipfile.ZipFile(book, "a") as archive:
        archive.writestr(large_path, large_payload, zipfile.ZIP_STORED)
    monkeypatch.setattr(editor_module, "MAX_DIRECT_IMAGE_ENCODED_BYTES", 512 * 1024)
    tab = EditorTab()
    qtbot.addWidget(tab)
    assert tab.open_epub(book)

    tab._show_file(large_path)
    assert "zbyt duży" in tab.info_panel.text().lower()
    tab.edit_toggle.setChecked(True)
    tab._select_path(_CHAPTER)
    cursor = tab.code_editor.editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.insertText('<html xmlns="http://www.w3.org/1999/xhtml"><body>mała zmiana</body></html>')
    assert tab._save_current()
    tab._save_epub()

    with zipfile.ZipFile(book) as archive:
        saved = archive.read(large_path)
        assert saved == large_payload
        assert len(saved) == len(large_payload)
        assert "zbyt duży".encode() not in saved.lower()


def test_dimension_rejected_image_cannot_receive_stale_editor_content(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Odrzucony raster czyści stale QTextDocument i blokuje Ctrl+S dla obrazu."""
    internal = "OEBPS/images/huge.bmp"
    header_size = 54
    huge_bmp = (
        b"BM"
        + struct.pack("<IHHI", header_size, 0, 0, header_size)
        + struct.pack("<IiiHHIIiiII", 40, 9_000, 9_000, 1, 32, 0, 0, 0, 0, 0, 0)
    )
    book = _make_single_resource_epub(
        tmp_path / "huge-raster.epub", internal, "image/bmp", huge_bmp
    )
    tab = EditorTab()
    qtbot.addWidget(tab)
    assert tab.open_epub(book)
    tab.edit_toggle.setChecked(True)
    tab.code_editor.load("stale text", None)
    cursor = tab.code_editor.editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" modified")
    assert tab.code_editor.is_modified()

    tab._show_file(internal)

    assert tab.code_editor.get_text() == ""
    assert not tab.code_editor.is_modified()
    assert tab.code_editor.read_only
    assert not tab._save_current()
    assert internal not in tab._dirty
    with zipfile.ZipFile(book) as archive:
        assert archive.read(internal) == huge_bmp
