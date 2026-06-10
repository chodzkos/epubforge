"""Testy zakładki GUI konwersji do KFX."""

# ruff: noqa: E402

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

tk = pytest.importorskip("tkinter")

from epubforge.converters import ConversionResult, KfxOptions, MobiOptions
from epubforge.core import Tool
from epubforge.gui.tabs import kfx as kfx_module
from epubforge.gui.tabs.kfx import KfxTab

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
        "calibre_ebook_convert": Tool(
            "calibre_ebook_convert",
            Path("/bin/ebook-convert"),
            available=True,
        ),
        "kindle_previewer": Tool("kindle_previewer", None, available=False),
    }


def test_kfx_tab_creates_without_errors(root: tk.Tk) -> None:
    """Zakładka tworzy się z Calibre jako domyślnym silnikiem."""
    tab = KfxTab(root, tools=_tools())
    tab.pack(fill="both", expand=True)
    root.update_idletasks()

    assert tab.winfo_exists()
    assert tab.file_list.files() == []
    assert tab.engine_var.get() == "calibre"
    assert tab.fix_epub_toggle.get() is True
    assert tab.kp3_warning_text.winfo_manager() == ""


def test_kfx_tab_builds_options_and_shows_kp3_warning(root: tk.Tk) -> None:
    """Wybranie KP3 ustawia opcje i pokazuje pole tekstowe z poradami."""
    tab = KfxTab(root, tools=_tools())

    tab.engine_var.set("kindle-previewer")
    tab.fix_epub_toggle.set(False)
    tab._refresh_kp3_warning()

    opts = tab._build_options_obj()
    warning = tab.kp3_warning_text.get("1.0", "end-1c")

    assert isinstance(opts, KfxOptions)
    assert opts.engine == "kindle-previewer"
    assert opts.fix_epub_first is False
    assert tab.kp3_warning_text.winfo_manager() == "pack"
    assert "niestandardowe fonty" in warning
    assert "uprość CSS" in warning


def test_kfx_tab_blocks_conversion_without_output_dir(root: tk.Tk, tmp_path: Path) -> None:
    """Bez katalogu docelowego konwersja nie rusza."""
    tab = KfxTab(root, tools=_tools())
    book = tmp_path / "book.epub"
    tab.file_list.add_files([book])

    tab.output_dir.set("")
    tab._run_conversion()

    assert tab._running is False
    assert tab.progress_var.get() == 0
    assert "folder wyjściowy" in tab.status_var.get()


def test_kfx_tab_runs_conversion_in_worker(
    root: tk.Tk,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker woła prawdziwe API to_kfx przez import modułu dla każdego pliku."""
    calls: list[tuple[Path, Path, KfxOptions]] = []

    def fake_to_kfx(source: Path, target_dir: Path, options: KfxOptions) -> ConversionResult:
        calls.append((source, target_dir, options))
        return ConversionResult(
            success=True,
            output_path=target_dir / f"{source.stem}.kfx",
            log="done",
            engine="calibre",
        )

    monkeypatch.setattr(kfx_module, "to_kfx", fake_to_kfx)

    tab = KfxTab(root, tools=_tools())
    book = tmp_path / "book.epub"
    output = tmp_path / "out"
    options = KfxOptions(engine="calibre", fix_epub_first=True)

    tab._run_worker([book], output, options)
    root.update()

    assert calls == [(book, output, options)]
    assert tab.progress_var.get() == 1
    assert tab.status_var.get() == "Zakończono: 1/1 OK"


def test_kfx_tab_run_button_starts_thread(
    root: tk.Tk,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kliknięcie przycisku tworzy wątek z plikami, folderem i KfxOptions."""
    calls: list[tuple[list[Path], Path, KfxOptions]] = []

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
        self: KfxTab,
        files: list[Path],
        target_dir: Path,
        options: KfxOptions,
    ) -> None:
        calls.append((files, target_dir, options))

    monkeypatch.setattr(kfx_module.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(KfxTab, "_run_worker", fake_worker)

    tab = KfxTab(root, tools=_tools())
    book = tmp_path / "book.epub"
    output = tmp_path / "out"
    tab.file_list.add_files([book])
    tab.output_dir.set(str(output))

    tab._run_conversion()

    assert len(calls) == 1
    files, target_dir, options = calls[0]
    assert files == [book]
    assert target_dir == output
    assert options.engine == "calibre"
    assert options.fix_epub_first is True


def test_format_switch_shows_mobi_engine(root: tk.Tk) -> None:
    """Wybór formatu MOBI pokazuje sekcję silnika MOBI i chowa sekcję KFX."""
    tab = KfxTab(root, tools=_tools())
    tab.pack(fill="both", expand=True)
    root.update_idletasks()

    # Domyślnie KFX: sekcja KFX widoczna, MOBI ukryta.
    assert tab.kfx_engine_section.winfo_manager() == "pack"
    assert tab.mobi_engine_section.winfo_manager() == ""

    tab.format_var.set("mobi")
    tab._on_format_change()
    root.update_idletasks()

    assert tab.mobi_engine_section.winfo_manager() == "pack"
    assert tab.kfx_engine_section.winfo_manager() == ""
    assert "MOBI" in tab.convert_button.cget("text")


def test_mobi_worker_calls_to_mobi(
    root: tk.Tk,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker MOBI woła to_mobi z celem o właściwym rozszerzeniu i opcjami."""
    calls: list[tuple[Path, Path, MobiOptions]] = []

    def fake_to_mobi(source: Path, target: Path, options: MobiOptions) -> ConversionResult:
        calls.append((source, target, options))
        return ConversionResult(True, target, "done", "calibre")

    monkeypatch.setattr(kfx_module, "to_mobi", fake_to_mobi)

    tab = KfxTab(root, tools=_tools())
    tab.format_var.set("azw3")
    tab.mobi_engine_var.set("calibre")
    options = tab._build_mobi_options()

    book = tmp_path / "book.epub"
    output = tmp_path / "out"
    tab._run_mobi_worker([book], output, options)
    root.update()

    assert len(calls) == 1
    source, target, opts = calls[0]
    assert source == book
    assert target == output / "book.azw3"
    assert opts.fmt == "azw3"
    assert opts.engine == "calibre"
    assert tab.status_var.get() == "Zakończono: 1/1 OK"
