"""Testy zakładki GUI do naprawy EPUB (PySide6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pytestqt.qtbot import QtBot

from epubforge.core import Tool
from epubforge.fixers import CssFixOptions, HyphenationOptions, TypographyOptions
from epubforge.gui.tabs import fixer as fixer_module
from epubforge.gui.tabs.fixer import FixerTab, _run_fix_worker

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
    )

    assert (succeeded, total) == (1, 1)
    assert last == fixed
    assert hyphen_calls and css_calls
