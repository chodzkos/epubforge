"""Testy panelu Szukaj/Zamień w zakładce Edytor (PySide6, offscreen)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from epubforge.gui.tabs.editor import EditorTab

pytestmark = pytest.mark.gui

_CHAPTER_PATH = "OEBPS/text/chapter1.xhtml"
_CHAPTER = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c</title></head>'
    "<body>\n<p>Ala ma kota, a kot ma Alę.</p>\n</body></html>"
)


def _build_epub(tmp_path: Path) -> Path:
    epub_path = tmp_path / "book.epub"
    container = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="b">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="b">id</dc:identifier><dc:title>t</dc:title>'
        "<dc:language>pl</dc:language></metadata>"
        '<manifest><item id="c1" href="text/chapter1.xhtml" media-type="application/xhtml+xml"/>'
        '</manifest><spine><itemref idref="c1"/></spine></package>'
    )
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", opf.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/text/chapter1.xhtml", _CHAPTER.encode(), zipfile.ZIP_DEFLATED)
    return epub_path


def _open_tab(qtbot: QtBot, tmp_path: Path) -> EditorTab:
    tab = EditorTab()
    qtbot.addWidget(tab)
    assert tab.open_epub(_build_epub(tmp_path))
    return tab


def test_toggle_shows_panel(qtbot: QtBot, tmp_path: Path) -> None:
    """Ctrl+Shift+F (toggle) pokazuje i chowa panel."""
    tab = _open_tab(qtbot, tmp_path)
    assert tab.search_panel.isHidden() is True
    tab._toggle_search_panel()
    assert tab.search_panel.isHidden() is False
    tab._toggle_search_panel()
    assert tab.search_panel.isHidden() is True


def test_search_current_file_populates_results(qtbot: QtBot, tmp_path: Path) -> None:
    """Szukanie w bieżącym pliku wypełnia drzewo wyników trafieniami."""
    tab = _open_tab(qtbot, tmp_path)
    tab._select_path(_CHAPTER_PATH)
    panel = tab.search_panel
    panel.scope_current.setChecked(True)
    panel.search_field.setText("kot")
    panel._on_search()
    qtbot.waitUntil(lambda: not panel._searching, timeout=3000)

    assert panel.results.topLevelItemCount() == 1
    group = panel.results.topLevelItem(0)
    assert group is not None
    assert group.childCount() == 2  # „kota" i „kot"


def test_search_whole_epub_worker(qtbot: QtBot, tmp_path: Path) -> None:
    """Szukanie w całym EPUB biegnie w Workerze i zwraca wyniki."""
    tab = _open_tab(qtbot, tmp_path)
    panel = tab.search_panel
    panel.scope_all.setChecked(True)
    panel.search_field.setText("Ala")
    panel._on_search()

    qtbot.waitUntil(lambda: not panel._searching, timeout=3000)
    assert panel.results.topLevelItemCount() == 1


def test_double_click_result_jumps(qtbot: QtBot, tmp_path: Path) -> None:
    """Dwuklik wyniku ustawia kursor edytora na linii trafienia."""
    tab = _open_tab(qtbot, tmp_path)
    tab._select_path(_CHAPTER_PATH)
    panel = tab.search_panel
    panel.scope_current.setChecked(True)
    panel.search_field.setText("kot")
    panel._on_search()
    qtbot.waitUntil(lambda: not panel._searching, timeout=3000)

    group = panel.results.topLevelItem(0)
    assert group is not None
    child = group.child(0)
    assert child is not None
    panel._on_result_double_clicked(child, 0)
    # Trafienie jest w 2. linii (1-based) → kursor w bloku 1 (0-based).
    assert tab.code_editor.editor.textCursor().blockNumber() == 1


def test_replace_all_updates_buffer_and_marks_dirty(qtbot: QtBot, tmp_path: Path) -> None:
    """„Zamień wszystkie" pisze do bufora EPUB i oznacza plik jako zmieniony."""
    tab = _open_tab(qtbot, tmp_path)
    tab._select_path(_CHAPTER_PATH)
    panel = tab.search_panel
    panel.scope_all.setChecked(True)
    panel.search_field.setText("kot")
    panel.replace_field.setText("pies")
    panel._on_replace_all()
    qtbot.waitUntil(lambda: not panel._searching, timeout=3000)

    assert tab._epub is not None
    assert b"pies" in tab._epub.read_file(_CHAPTER_PATH)
    assert _CHAPTER_PATH in tab._dirty  # „Zapisz EPUB" zobaczy zmianę
    assert tab.save_epub_button.isEnabled()


def test_bad_regex_shows_status(qtbot: QtBot, tmp_path: Path) -> None:
    """Błędny regex nie wywala panelu — pokazuje komunikat w statusie."""
    tab = _open_tab(qtbot, tmp_path)
    tab._select_path(_CHAPTER_PATH)
    panel = tab.search_panel
    panel.scope_current.setChecked(True)
    panel.regex_check.setChecked(True)
    panel.search_field.setText("(niezamkniety")
    panel._on_search()
    qtbot.waitUntil(lambda: not panel._searching, timeout=3000)
    assert panel.status_label.text()
    assert panel.results.topLevelItemCount() == 0


def test_replace_all_disables_cancel_and_locks_editor(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replace All nie idzie ścieżką cancel (gubi raport) i blokuje edytor."""
    import threading

    import epubforge.gui.widgets.search_panel as search_mod
    from epubforge.core.search import ReplaceReport, replace_in_epub

    started = threading.Event()
    release = threading.Event()
    original = replace_in_epub

    def blocked(*args: object, **kwargs: object) -> ReplaceReport:
        started.set()
        assert release.wait(timeout=3)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(search_mod, "replace_in_epub", blocked)
    tab = _open_tab(qtbot, tmp_path)
    tab._select_path(_CHAPTER_PATH)
    tab.edit_toggle.setChecked(True)
    tab._apply_read_only()
    assert tab.code_editor.read_only is False
    panel = tab.search_panel
    panel.scope_all.setChecked(True)
    panel.search_field.setText("kot")
    panel.replace_field.setText("pies")
    panel._on_replace_all()
    qtbot.waitUntil(started.is_set, timeout=3000)
    assert panel.cancel_button.isEnabled() is False
    assert tab.code_editor.read_only is True
    release.set()
    qtbot.waitUntil(lambda: not panel._searching, timeout=3000)
    assert tab.code_editor.read_only is False
    assert _CHAPTER_PATH in tab._dirty


def test_replace_timeout_keeps_status_without_research(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Timeout zamiany nie odświeża szukania tym samym wzorcem (nie nadpisuje statusu)."""
    epub_path = tmp_path / "book.epub"
    container = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="b">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="b">id</dc:identifier><dc:title>t</dc:title>'
        "<dc:language>pl</dc:language></metadata>"
        '<manifest><item id="a" href="text/a.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="z" href="text/z.xhtml" media-type="application/xhtml+xml"/>'
        '</manifest><spine><itemref idref="a"/></spine></package>'
    )
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", opf.encode(), zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/text/a.xhtml", b"aaa", zipfile.ZIP_DEFLATED)
        zf.writestr("OEBPS/text/z.xhtml", ("a" * 28 + "!").encode(), zipfile.ZIP_DEFLATED)
    tab = EditorTab()
    qtbot.addWidget(tab)
    assert tab.open_epub(epub_path)
    panel = tab.search_panel
    panel.scope_all.setChecked(True)
    panel.regex_check.setChecked(True)
    panel.search_field.setText(r"(a|a)+$")
    panel.replace_field.setText("z")
    panel._on_replace_all()
    qtbot.waitUntil(lambda: not panel._searching, timeout=5000)
    status = panel.status_label.text()
    assert "Zamieniono" in status or "pominięto" in status
    assert "limit czasu" not in status or "pominięto" in status
    # Nie nadpisane komunikatem samego SearchPatternError z powtórzonego search.
    assert not status.startswith("Wyrażenie regularne")
