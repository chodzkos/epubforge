"""Testy zakładki GUI do naprawy EPUB."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    import tkinter as tk
else:
    tk = pytest.importorskip("tkinter")

from epubforge.core import Tool
from epubforge.fixers import CssFixOptions, HyphenationOptions
from epubforge.gui.tabs.fixer import FixerTab

pytestmark = pytest.mark.gui


@pytest.fixture
def root() -> Iterator[tk.Tk]:
    """Tworzy root tkinter albo pomija test, gdy środowisko nie ma display."""
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    window.withdraw()
    try:
        yield window
    finally:
        window.destroy()


def _tools() -> dict[str, Tool]:
    return {
        "calibre_viewer": Tool("calibre_viewer", Path("/bin/ebook-viewer"), available=True),
    }


def test_fixer_tab_creates_without_errors(root: tk.Tk) -> None:
    """Zakładka tworzy się i buduje wymagane sekcje bez wyjątku."""
    tab = FixerTab(root, tools=_tools())
    tab.pack(fill="both", expand=True)
    root.update_idletasks()

    assert tab.winfo_exists()
    assert tab.file_list.files() == []
    assert "disabled" in tab.preview_button.state()


def test_fixer_tab_builds_correct_options(root: tk.Tk) -> None:
    """Zakładka buduje prawdziwe obiekty opcji fixerów z wartości UI."""
    tab = FixerTab(root, tools=_tools())

    tab.hyphen_enabled_toggle.set(True)
    tab.hyphen_lang_var.set("en_US")
    tab.hyphen_method_var.set("css")
    tab.hyphen_skip_headers_toggle.set(False)

    tab.css_remove_colors_toggle.set(True)
    tab.css_remove_fonts_toggle.set(False)
    tab.css_inject_reset_toggle.set(False)
    tab.css_replace_justify_toggle.set(True)
    tab.css_skip_hyphen_headers_toggle.set(False)
    tab.css_book_margin_toggle.set(True)
    tab.css_margin_px_var.set("30")

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


def test_fixer_tab_runs_worker_thread(
    root: tk.Tk,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kliknięcie „Napraw” uruchamia wątek roboczy z poprawnymi argumentami."""
    calls: list[tuple[list[Path], HyphenationOptions | None, CssFixOptions]] = []

    class ImmediateThread:
        def __init__(
            self,
            *,
            target: Any,
            args: tuple[Any, ...],
            daemon: bool,
        ) -> None:
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            self.target(*self.args)

    def fake_worker(
        self: FixerTab,
        files: list[Path],
        hyphen_opts: HyphenationOptions | None,
        css_opts: CssFixOptions,
    ) -> None:
        calls.append((files, hyphen_opts, css_opts))

    monkeypatch.setattr("epubforge.gui.tabs.fixer.threading.Thread", ImmediateThread)
    monkeypatch.setattr(FixerTab, "_run_worker", fake_worker)

    tab = FixerTab(root, tools=_tools())
    book = tmp_path / "book.epub"
    tab.file_list.add_files([book])
    tab._run_fix()

    assert len(calls) == 1
    files, hyphen_opts, css_opts = calls[0]
    assert files == [book]
    assert isinstance(hyphen_opts, HyphenationOptions)
    assert isinstance(css_opts, CssFixOptions)


def test_fixer_tab_preview_uses_calibre_viewer(
    root: tk.Tk,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Podgląd po sukcesie uruchamia wykryty Calibre Viewer z plikiem wynikowym."""
    calls: list[list[str]] = []

    def fake_popen(cmd: list[str], **kwargs: Any) -> object:
        calls.append(cmd)
        return object()

    monkeypatch.setattr("epubforge.gui.tabs.fixer.subprocess.Popen", fake_popen)

    tab = FixerTab(root, tools=_tools())
    fixed = tmp_path / "book.epub"
    tab._finish_fix(1, 1, fixed)
    tab._view_result()

    assert calls == [["/bin/ebook-viewer", str(fixed)]]
