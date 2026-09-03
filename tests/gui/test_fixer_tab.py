"""Testy zakładki GUI do naprawy EPUB (PySide6)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from epubforge.core import Epub, Tool
from epubforge.fixers import CssFixOptions, HyphenationOptions, TypographyOptions
from epubforge.gui.tabs import fixer as fixer_module
from epubforge.gui.tabs.fixer import FixerTab, _run_fix_worker, _run_upgrade_worker

pytestmark = pytest.mark.gui


def _tools() -> dict[str, Tool]:
    return {"calibre_viewer": Tool("calibre_viewer", Path("/bin/ebook-viewer"), available=True)}


def _select_method(tab: FixerTab, method: str) -> None:
    for button in tab.hyphen_method_group.buttons():
        if button.property("method") == method:
            button.setChecked(True)


def test_fixer_creates_with_preview_disabled(qtbot: QtBot) -> None:
    """Zakładka tworzy się; podgląd jest wyłączony do pierwszego sukcesu."""
    tab = FixerTab(tools=_tools())
    qtbot.addWidget(tab)
    assert tab.file_list.files() == []
    assert tab.preview_button.isEnabled() is False
    assert tab.fix_button.isEnabled() is False


def test_fixer_builds_correct_options(qtbot: QtBot) -> None:
    """Zakładka buduje prawdziwe obiekty opcji fixerów z wartości UI."""
    tab = FixerTab(tools=_tools())
    qtbot.addWidget(tab)

    tab.hyphen_enabled.setChecked(True)
    tab.hyphen_lang_box.setCurrentText("en_US")
    _select_method(tab, "css")
    tab.hyphen_skip_headers.setChecked(False)

    tab.css_remove_colors.setChecked(True)
    tab.css_remove_fonts.setChecked(False)
    tab.css_inject_reset.setChecked(False)
    tab.css_replace_justify.setChecked(True)
    tab.css_skip_hyphen_headers.setChecked(False)
    tab.css_book_margin.setChecked(True)
    tab.margin_spin.setValue(30)

    hyphen_opts = tab._build_hyphen_options()
    css_opts = tab._build_css_options()

    assert isinstance(hyphen_opts, HyphenationOptions)
    assert hyphen_opts.language == "en_US"
    assert hyphen_opts.method == "css"
    assert hyphen_opts.skip_headers is False

    assert isinstance(css_opts, CssFixOptions)
    assert css_opts.remove_colors is True
    assert css_opts.remove_fonts is False
    assert css_opts.inject_reset is False
    assert css_opts.replace_justify == "left"
    assert css_opts.skip_hyphenation_headers is False
    assert css_opts.inject_book_margin_px == 30


def test_fixer_disabled_hyphenation_returns_none(qtbot: QtBot) -> None:
    """Wyłączony przełącznik hyphenacji daje None (fixer pomija dzielenie)."""
    tab = FixerTab(tools=_tools())
    qtbot.addWidget(tab)
    tab.hyphen_enabled.setChecked(False)
    assert tab._build_hyphen_options() is None


def test_fixer_warning_visible_only_for_soft_hyphen(qtbot: QtBot) -> None:
    """Ostrzeżenie o soft-hyphen pokazuje się tylko dla tej metody."""
    tab = FixerTab(tools=_tools())
    qtbot.addWidget(tab)
    _select_method(tab, "soft-hyphen")
    assert tab.hyphen_warning_label.isHidden() is False
    _select_method(tab, "css")
    assert tab.hyphen_warning_label.isHidden() is True


def test_fixer_run_starts_worker(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_worker: type
) -> None:
    """„Napraw" startuje workera z plikami i opcjami fixerów."""
    monkeypatch.setattr(fixer_module, "Worker", fake_worker)
    tab = FixerTab(tools=_tools())
    qtbot.addWidget(tab)
    book = tmp_path / "book.epub"
    tab.file_list.add_files([book])
    tab._run_fix()

    fn, args, _kwargs = fake_worker.captured[-1]  # type: ignore[attr-defined]
    assert fn is _run_fix_worker
    assert args[0] == [book]
    assert isinstance(args[1], (TypographyOptions, type(None)))
    assert isinstance(args[2], (HyphenationOptions, type(None)))
    assert isinstance(args[3], CssFixOptions)


def test_fixer_preview_uses_calibre_viewer(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Podgląd po sukcesie uruchamia wykryty Calibre Viewer z plikiem wynikowym."""
    calls: list[list[str]] = []

    def fake_popen(cmd: list[str], **kwargs: Any) -> object:
        calls.append(cmd)
        return object()

    monkeypatch.setattr("epubforge.gui.tabs.fixer.subprocess.Popen", fake_popen)

    tab = FixerTab(tools=_tools())
    qtbot.addWidget(tab)
    fixed = tmp_path / "book.epub"
    tab._finish_fix((1, 1, fixed))
    assert tab.preview_button.isEnabled() is True
    tab._view_result()

    assert calls == [[str(Path("/bin/ebook-viewer")), str(fixed)]]


def test_upgrade_button_confirms_and_starts_worker(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_worker: type
) -> None:
    """„Uaktualnij do EPUB 3" po potwierdzeniu startuje workera z plikami i flagą NCX."""
    monkeypatch.setattr(fixer_module, "Worker", fake_worker)
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    tab = FixerTab(tools=_tools())
    qtbot.addWidget(tab)
    book = tmp_path / "book.epub"
    tab.file_list.add_files([book])
    assert tab.upgrade_button.isEnabled() is True
    tab.upgrade_drop_ncx.setChecked(True)
    tab._run_upgrade()

    fn, args, _kwargs = fake_worker.captured[-1]  # type: ignore[attr-defined]
    assert fn is _run_upgrade_worker
    assert args == ([book], True)  # (files, drop_ncx)


def test_upgrade_cancelled_does_not_start_worker(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_worker: type
) -> None:
    """Odmowa w oknie potwierdzenia nie uruchamia workera."""
    monkeypatch.setattr(fixer_module, "Worker", fake_worker)
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
    )
    tab = FixerTab(tools=_tools())
    qtbot.addWidget(tab)
    tab.file_list.add_files([tmp_path / "book.epub"])
    tab._run_upgrade()
    assert fake_worker.captured == []  # type: ignore[attr-defined]


def test_run_upgrade_worker_upgrades_epub2(epub2_epub: Path) -> None:
    """Worker modernizuje EPUB 2 → 3, zapisuje i zwraca licznik sukcesów."""
    lines: list[tuple[str, str]] = []
    succeeded, total, last = _run_upgrade_worker(
        lambda text, level: lines.append((text, level)),
        lambda current, total_: None,
        [epub2_epub],
        False,
    )
    assert (succeeded, total) == (1, 1)
    assert last == epub2_epub
    with Epub(epub2_epub) as epub:
        assert b'version="3.0"' in epub.read_file(epub.opf_path)


def test_run_upgrade_worker_skips_epub3(sample_epub: Path) -> None:
    """Worker pomija plik już w EPUB 3 (nie liczy jako sukces upgrade)."""
    messages: list[str] = []
    succeeded, total, _last = _run_upgrade_worker(
        lambda text, level: messages.append(text),
        lambda current, total_: None,
        [sample_epub],
        False,
    )
    assert (succeeded, total) == (0, 1)
    assert any("Już EPUB 3" in message for message in messages)


def test_run_fix_worker_calls_fixers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Funkcja robocza otwiera Epub, woła hyphenate/fix_css i zwraca licznik."""
    hyphen_calls: list[Any] = []
    css_calls: list[Any] = []
    fixed = tmp_path / "book.epub"

    class FakeEpub:
        def __init__(self, path: Path) -> None:
            self.path = path

        def __enter__(self) -> FakeEpub:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def save(self) -> Path:
            return fixed

    monkeypatch.setattr(fixer_module, "Epub", FakeEpub)
    monkeypatch.setattr(fixer_module, "hyphenate", lambda epub, opts: hyphen_calls.append(opts))
    monkeypatch.setattr(fixer_module, "fix_css", lambda epub, opts: css_calls.append(opts))

    succeeded, total, last = _run_fix_worker(
        lambda text, level: None,
        lambda current, total_: None,
        [fixed],
        None,
        HyphenationOptions(),
        CssFixOptions(),
        None,
        None,
        None,
    )

    assert (succeeded, total) == (1, 1)
    assert last == fixed
    assert hyphen_calls and css_calls


def test_main_window_close_is_blocked_during_fixer_work(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qapp: object,
) -> None:
    """Zamknięcie aplikacji nie niszczy GUI, gdy Fixer nadal zapisuje EPUB-y."""
    from chodzkos_gui_kit.qt.theme import ThemeManager
    from PySide6.QtWidgets import QApplication

    from epubforge.core.config import ConfigStore
    from epubforge.gui.app import MainWindow

    assert isinstance(qapp, QApplication)
    started = threading.Event()
    release = threading.Event()

    def blocked_worker(
        _emit_line: object, _emit_progress: object, *_args: object
    ) -> tuple[int, int, None]:
        started.set()
        release.wait(timeout=5)
        return 0, 1, None

    monkeypatch.setattr(fixer_module, "_run_fix_worker", blocked_worker)
    notices: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        staticmethod(lambda *args, **_kwargs: notices.append(str(args[2]))),
    )
    store = ConfigStore("epubforge", path=tmp_path / "config.json")
    window = MainWindow(
        tmp_path / "config.json",
        store,
        {"pandoc": Tool("pandoc", None, available=False)},
        ThemeManager(qapp, store),
    )
    qtbot.addWidget(window)
    window.fixer_tab.file_list.add_files([tmp_path / "book.epub"])
    window.fixer_tab._run_fix()
    qtbot.waitUntil(started.is_set, timeout=3000)
    worker = window.fixer_tab._worker
    assert worker is not None and worker.isRunning()

    try:
        event = QCloseEvent()
        window.closeEvent(event)

        assert event.isAccepted() is False
        assert window.fixer_tab.is_running() is True
        assert worker.isRunning()
        assert any("Poczekaj" in notice for notice in notices)
    finally:
        release.set()
        qtbot.waitUntil(lambda: not window.fixer_tab._running, timeout=3000)
        worker.wait(3000)
