"""Testy panelu Szukaj/Zamień w zakładce Edytor (PySide6, offscreen)."""

from __future__ import annotations

import threading
import zipfile
from pathlib import Path

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from epubforge.core.search import ReplaceReport, SearchHit, SearchResults, replace_in_epub
from epubforge.gui.tabs.editor import EditorTab
from epubforge.gui.widgets.search_panel import SearchReplacePanel

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


def _start_blocked_replace(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    tab: EditorTab | None = None,
) -> tuple[EditorTab, SearchReplacePanel, threading.Event, threading.Event]:
    """Uruchamia Replace All i trzyma workera na barierze (bez sleep)."""
    import epubforge.gui.widgets.search_panel as search_mod

    started = threading.Event()
    release = threading.Event()
    original = replace_in_epub

    def blocked(*args: object, **kwargs: object) -> ReplaceReport:
        started.set()
        assert release.wait(timeout=3)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(search_mod, "replace_in_epub", blocked)
    if tab is None:
        tab = _open_tab(qtbot, tmp_path)
    tab._select_path(_CHAPTER_PATH)
    panel = tab.search_panel
    panel.scope_all.setChecked(True)
    panel.search_field.setText("kot")
    panel.replace_field.setText("pies")
    panel._on_replace_all()
    qtbot.waitUntil(started.is_set, timeout=3000)
    return tab, panel, started, release


def _start_blocked_search(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[EditorTab, SearchReplacePanel, threading.Event, threading.Event]:
    """Uruchamia search i trzyma odczyt starego EPUB-a na jawnej barierze."""
    import epubforge.gui.widgets.search_panel as search_mod

    started = threading.Event()
    release = threading.Event()

    def blocked(*_args: object, **_kwargs: object) -> SearchResults:
        started.set()
        assert release.wait(timeout=3)
        return _many_hits(1)

    monkeypatch.setattr(search_mod, "search_epub", blocked)
    tab = _open_tab(qtbot, tmp_path)
    panel = tab.search_panel
    panel.search_field.setText("needle")
    panel._on_search()
    qtbot.waitUntil(started.is_set, timeout=3000)
    return tab, panel, started, release


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


def _many_hits(count: int, *, truncated: bool = False) -> SearchResults:
    """Tworzy lekki bounded result set bez pliku-fixture."""
    return SearchResults(
        [SearchHit(_CHAPTER_PATH, line, 1, f"needle {line}") for line in range(1, count + 1)],
        truncated=truncated,
    )


def test_large_result_set_populates_only_first_page(qtbot: QtBot, tmp_path: Path) -> None:
    """GUI nie tworzy naraz itemu Qt dla każdego trafienia z bufora core."""
    tab = _open_tab(qtbot, tmp_path)
    panel = tab.search_panel

    panel._populate_results(_many_hits(1001, truncated=True))

    group = panel.results.topLevelItem(0)
    assert group is not None
    assert panel.RESULT_PAGE_SIZE == 500
    assert group.childCount() == 500
    assert panel.show_more_button.isEnabled()
    assert "co najmniej" in panel.status_label.text()


def test_show_more_uses_buffer_without_duplicates(qtbot: QtBot, tmp_path: Path) -> None:
    """Kolejne strony są dokładane z bufora raz, bez ponownego search i duplikatów."""
    tab = _open_tab(qtbot, tmp_path)
    panel = tab.search_panel
    panel._populate_results(_many_hits(1001))

    panel._show_more_results()
    panel._show_more_results()

    group = panel.results.topLevelItem(0)
    assert group is not None
    assert group.childCount() == 1001
    locations = [group.child(index).data(0, 256) for index in range(group.childCount())]
    assert len(locations) == len(set(locations))
    assert panel.show_more_button.isEnabled() is False


def test_empty_result_resets_pagination_state(qtbot: QtBot, tmp_path: Path) -> None:
    """Pusty wynik usuwa poprzedni bufor, itemy i możliwość pokazania kolejnej strony."""
    tab = _open_tab(qtbot, tmp_path)
    panel = tab.search_panel
    panel._populate_results(_many_hits(1001))

    panel._populate_results(SearchResults())

    assert panel.results.topLevelItemCount() == 0
    assert panel.show_more_button.isEnabled() is False
    assert panel._result_hits == []


def test_new_epub_resets_search_results(qtbot: QtBot, tmp_path: Path) -> None:
    """Otwarcie nowej książki czyści strony i unieważnia callback starego search."""
    tab = _open_tab(qtbot, tmp_path)
    panel = tab.search_panel
    panel._populate_results(_many_hits(1001))
    old_generation = panel._search_generation
    other_dir = tmp_path / "other-search"
    other_dir.mkdir()

    assert tab.open_epub(_build_epub(other_dir))
    panel._on_search_done(_many_hits(1), old_generation)

    assert panel.results.topLevelItemCount() == 0
    assert panel._result_hits == []


def test_new_query_resets_previous_pagination(qtbot: QtBot, tmp_path: Path) -> None:
    """Start nowego query usuwa stare itemy przed uruchomieniem workera."""
    tab = _open_tab(qtbot, tmp_path)
    panel = tab.search_panel
    panel.search_field.setText("needle")
    panel._populate_results(_many_hits(1001))
    panel.search_field.setText("absent")

    assert panel.results.topLevelItemCount() == 0
    assert panel._result_hits == []

    panel._on_search()
    qtbot.waitUntil(lambda: not panel._searching, timeout=3000)


def test_clearing_query_resets_previous_results(qtbot: QtBot, tmp_path: Path) -> None:
    """Wyczyszczenie pola natychmiast usuwa trafienia poprzedniego zapytania."""
    tab = _open_tab(qtbot, tmp_path)
    panel = tab.search_panel
    panel.search_field.setText("needle")
    panel._populate_results(_many_hits(1001))

    panel.search_field.clear()

    assert panel.results.topLevelItemCount() == 0
    assert panel._result_hits == []
    assert panel.show_more_button.isEnabled() is False


def test_open_and_dispose_are_blocked_while_search_reads_epub(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lifecycle nie zamyka Epub-a pod aktywnym workerem search."""
    tab, panel, _started, release = _start_blocked_search(qtbot, tmp_path, monkeypatch)
    epub = tab._epub
    assert epub is not None
    other_dir = tmp_path / "search-lifecycle"
    other_dir.mkdir()
    other = _build_epub(other_dir)
    try:
        assert tab.open_epub(other) is False
        tab.dispose()
        assert tab._epub is epub
        assert epub._zip is not None
    finally:
        release.set()
        qtbot.waitUntil(lambda: not panel._searching, timeout=3000)


def test_search_cancel_is_cooperative(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anulowanie ustawia hook workera i nie aplikuje częściowego wyniku."""
    import epubforge.gui.widgets.search_panel as search_mod

    started = threading.Event()
    cancelled = threading.Event()

    def cancellable(*_args: object, **kwargs: object) -> SearchResults:
        should_cancel = kwargs["should_cancel"]
        started.set()
        assert callable(should_cancel)
        assert cancelled.wait(timeout=3) or should_cancel()
        return _many_hits(1)

    monkeypatch.setattr(search_mod, "search_epub", cancellable)
    tab = _open_tab(qtbot, tmp_path)
    panel = tab.search_panel
    panel.search_field.setText("needle")
    panel._on_search()
    qtbot.waitUntil(started.is_set, timeout=3000)

    panel._on_cancel()
    cancelled.set()
    qtbot.waitUntil(lambda: not panel._searching, timeout=3000)

    assert panel.results.topLevelItemCount() == 0
    assert "Anulowano" in panel.status_label.text()


def test_query_change_cancels_and_ignores_inflight_result(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Callback starego query nie odtwarza wyników po zmianie tekstu pola."""
    _tab, panel, _started, release = _start_blocked_search(qtbot, tmp_path, monkeypatch)

    panel.search_field.setText("different")
    release.set()
    qtbot.waitUntil(lambda: not panel._searching, timeout=3000)

    assert panel.results.topLevelItemCount() == 0
    assert panel._result_hits == []


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
    import epubforge.gui.widgets.search_panel as search_mod

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


def test_replace_timeout_keeps_status_without_research(qtbot: QtBot, tmp_path: Path) -> None:
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


def test_close_is_blocked_during_replace_all(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Close/dispose nie niszczy Epub, dopóki Replace All trzyma workera."""
    tab, panel, _started, release = _start_blocked_replace(qtbot, tmp_path, monkeypatch)
    epub = tab._epub
    assert epub is not None
    try:
        tab.dispose()
        assert tab._epub is epub
        assert epub._zip is not None
        assert epub.read_file(_CHAPTER_PATH)
        assert "Poczekaj" in tab.info_bar.text()
    finally:
        release.set()
        qtbot.waitUntil(lambda: not panel._searching, timeout=3000)


def test_save_is_blocked_during_replace_all(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Save EPUB nie woła Epub.save (reopen/snapshot) w trakcie Replace All."""
    tab, panel, _started, release = _start_blocked_replace(qtbot, tmp_path, monkeypatch)
    epub = tab._epub
    assert epub is not None
    tab._dirty[_CHAPTER_PATH] = "seed"
    saves: list[object] = []
    original_save = epub.save

    def spy_save(*args: Path, **kwargs: object) -> Path:
        saves.append((args, kwargs))
        return original_save(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(epub, "save", spy_save)
    try:
        tab._save_epub()
        assert saves == []
        assert epub._zip is not None
        assert tab.save_epub_button.isEnabled() is False
        assert "Poczekaj" in tab.info_bar.text()
    finally:
        release.set()
        qtbot.waitUntil(lambda: not panel._searching, timeout=3000)


def test_open_or_replace_document_is_blocked_during_replace_all(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otwarcie innego EPUB-a nie zamyka dokumentu używanego przez workera."""
    tab, panel, _started, release = _start_blocked_replace(qtbot, tmp_path, monkeypatch)
    epub = tab._epub
    assert epub is not None
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    other = _build_epub(other_dir)
    try:
        assert tab.open_epub(other) is False
        assert tab._epub is epub
        assert epub._zip is not None
        assert tab.open_button.isEnabled() is False
        assert "Poczekaj" in tab.info_bar.text()
    finally:
        release.set()
        qtbot.waitUntil(lambda: not panel._searching, timeout=3000)


def test_guard_is_released_after_replace_success(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Po udanej zamianie lifecycle i edytor wracają do użytku."""
    tab, panel, _started, release = _start_blocked_replace(qtbot, tmp_path, monkeypatch)
    release.set()
    qtbot.waitUntil(lambda: not panel._searching, timeout=3000)
    assert tab._mutation_guard is False
    assert tab.code_editor.read_only is True or tab.edit_toggle.isChecked() is False
    assert tab.open_button.isEnabled() is True
    assert tab.save_epub_button.isEnabled() is True
    assert _CHAPTER_PATH in tab._dirty
    after_dir = tmp_path / "after"
    after_dir.mkdir()
    other = _build_epub(after_dir)
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard)
    )
    assert tab.open_epub(other) is True


def test_guard_is_released_after_replace_failure(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wyjątek workera zdejmuje guard — dokument zostaje używalny."""
    import epubforge.gui.widgets.search_panel as search_mod

    started = threading.Event()

    def boom(*_args: object, **_kwargs: object) -> ReplaceReport:
        started.set()
        raise RuntimeError("boom-replace")

    monkeypatch.setattr(search_mod, "replace_in_epub", boom)
    tab = _open_tab(qtbot, tmp_path)
    tab._select_path(_CHAPTER_PATH)
    tab.edit_toggle.setChecked(True)
    tab._apply_read_only()
    panel = tab.search_panel
    panel.search_field.setText("kot")
    panel.replace_field.setText("pies")
    panel._on_replace_all()
    qtbot.waitUntil(lambda: not panel._searching, timeout=3000)
    assert started.is_set()
    assert tab._mutation_guard is False
    assert tab.code_editor.read_only is False
    assert tab.open_button.isEnabled() is True
    assert tab._epub is not None
    assert tab._epub._zip is not None
    assert "boom-replace" in panel.status_label.text()


def test_close_event_is_blocked_during_replace_all(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp: object
) -> None:
    """closeEvent okna nie dispose'uje EPUB-a podczas Replace All."""
    from chodzkos_gui_kit.qt.theme import ThemeManager
    from PySide6.QtWidgets import QApplication

    from epubforge.core import Tool
    from epubforge.core.config import ConfigStore
    from epubforge.gui.app import MainWindow

    assert isinstance(qapp, QApplication)
    store = ConfigStore("epubforge", path=tmp_path / "config.json")
    window = MainWindow(
        tmp_path / "config.json",
        store,
        {"pandoc": Tool("pandoc", None, available=False)},
        ThemeManager(qapp, store),
    )
    qtbot.addWidget(window)
    assert window.editor_tab.open_epub(_build_epub(tmp_path))
    notices: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda *a, **k: notices.append(str(a[2] if len(a) > 2 else k))),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    _tab, panel, _started, release = _start_blocked_replace(
        qtbot, tmp_path, monkeypatch, tab=window.editor_tab
    )
    epub = window.editor_tab._epub
    assert epub is not None
    try:
        event = QCloseEvent()
        window.closeEvent(event)
        assert event.isAccepted() is False
        assert window.editor_tab._epub is epub
        assert epub._zip is not None
        assert any("Poczekaj" in text for text in notices)
    finally:
        release.set()
        qtbot.waitUntil(lambda: not panel._searching, timeout=3000)


def test_partial_replace_timeout_marks_dirty_and_enables_save(qtbot: QtBot, tmp_path: Path) -> None:
    """Wcześniejsze zamiany + timeout zostają jako dirty; Save wraca po zejściu guardu."""
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
    assert tab._epub is not None
    assert tab._epub.read_file("OEBPS/text/a.xhtml") == b"z"
    assert "OEBPS/text/a.xhtml" in tab._dirty
    assert tab.has_unsaved_changes() is True
    assert tab._mutation_guard is False
    assert tab.save_epub_button.isEnabled() is True
    status = panel.status_label.text()
    assert "pominięto" in status or "Zamieniono" in status
    assert not status.startswith("Wyrażenie regularne")


def test_replace_exception_after_partial_mutation_keeps_dirty(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wyjątek po zapisie do bufora nie gubi dirty i zdejmuje guard."""
    import epubforge.gui.widgets.search_panel as search_mod

    started = threading.Event()

    def mutate_then_fail(epub: object, *_args: object, **_kwargs: object) -> ReplaceReport:
        started.set()
        epub.write_file(_CHAPTER_PATH, b"partial-mutation")  # type: ignore[union-attr]
        raise RuntimeError("after-write")

    monkeypatch.setattr(search_mod, "replace_in_epub", mutate_then_fail)
    tab = _open_tab(qtbot, tmp_path)
    panel = tab.search_panel
    panel.search_field.setText("kot")
    panel.replace_field.setText("pies")
    panel._on_replace_all()
    qtbot.waitUntil(lambda: not panel._searching, timeout=3000)
    assert started.is_set()
    assert tab._mutation_guard is False
    assert tab.code_editor.read_only is True or not tab.edit_toggle.isChecked()
    assert _CHAPTER_PATH in tab._dirty
    assert tab.has_unsaved_changes() is True
    assert tab.save_epub_button.isEnabled() is True
    assert tab._epub is not None
    assert tab._epub.read_file(_CHAPTER_PATH) == b"partial-mutation"


def test_stray_cancel_does_not_drop_replace_report(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Programowe cancel() podczas Replace All nie gubi mutacji ani nie zostawia busy."""
    tab, panel, _started, release = _start_blocked_replace(qtbot, tmp_path, monkeypatch)
    worker = panel._worker
    assert worker is not None
    panel._on_cancel()
    worker.cancel()
    release.set()
    qtbot.waitUntil(lambda: not panel._searching, timeout=3000)
    assert tab._mutation_guard is False
    assert _CHAPTER_PATH in tab._dirty
    assert tab.save_epub_button.isEnabled() is True
    assert "Anulowano" not in panel.status_label.text()


def test_cancel_tooltip_describes_search_not_only_whole_epub(qtbot: QtBot, tmp_path: Path) -> None:
    """Tooltip Anuluj obejmuje też wyszukiwanie w bieżącym pliku."""
    tab = _open_tab(qtbot, tmp_path)
    tip = tab.search_panel.cancel_button.toolTip()
    assert "Anuluj wyszukiwanie" in tip
    assert "całej publikacji" not in tip
