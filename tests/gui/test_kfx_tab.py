"""Testy zakładki GUI eksportu do formatów Kindle (PySide6)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from epubforge.converters import ConversionResult, KfxOptions, MobiOptions
from epubforge.core import Tool
from epubforge.gui.tabs import kfx as kfx_module
from epubforge.gui.tabs.kfx import KfxTab, _run_kfx_worker, _run_mobi_worker

pytestmark = pytest.mark.gui


def _tools() -> dict[str, Tool]:
    return {
        "calibre_ebook_convert": Tool(
            "calibre_ebook_convert", Path("/bin/ebook-convert"), available=True
        ),
        "kindle_previewer": Tool("kindle_previewer", None, available=False),
    }


def _select(group: object, prop: str, value: str) -> None:
    for button in group.buttons():  # type: ignore[attr-defined]
        if button.property(prop) == value:
            button.setChecked(True)


def test_kfx_creates_with_calibre_default(qtbot: QtBot) -> None:
    """Zakładka startuje z Calibre jako domyślnym silnikiem KFX."""
    tab = KfxTab(tools=_tools())
    qtbot.addWidget(tab)
    assert tab.file_list.files() == []
    assert tab._kfx_engine() == "calibre"
    assert tab.fix_epub_check.isChecked() is True
    assert tab.kp3_warning.isHidden() is True


def test_kfx_kp3_warning_and_options(qtbot: QtBot) -> None:
    """Wybór KP3 buduje KfxOptions i pokazuje ostrzeżenie z poradami."""
    tab = KfxTab(tools=_tools())
    qtbot.addWidget(tab)

    _select(tab.kfx_engine_group, "engine", "kindle-previewer")
    tab.fix_epub_check.setChecked(False)

    opts = tab._build_options_obj()
    assert isinstance(opts, KfxOptions)
    assert opts.engine == "kindle-previewer"
    assert opts.fix_epub_first is False
    assert tab.kp3_warning.isHidden() is False
    assert "niestandardowe fonty" in tab.kp3_warning.text()
    assert "uprość CSS" in tab.kp3_warning.text()


def test_kfx_format_switch_shows_mobi_engine(qtbot: QtBot) -> None:
    """Wybór formatu MOBI pokazuje sekcję silnika MOBI i chowa KFX."""
    tab = KfxTab(tools=_tools())
    qtbot.addWidget(tab)

    assert tab.kfx_engine_section.isHidden() is False
    assert tab.mobi_engine_section.isHidden() is True

    _select(tab.format_group, "fmt", "mobi")
    assert tab.mobi_engine_section.isHidden() is False
    assert tab.kfx_engine_section.isHidden() is True
    assert "MOBI" in tab.convert_button.text()


def test_kfx_prefills_output_from_first_file(qtbot: QtBot, tmp_path: Path) -> None:
    """Dodanie pierwszego pliku podpowiada jego katalog, gdy pole puste."""
    tab = KfxTab(tools=_tools())
    qtbot.addWidget(tab)
    book = tmp_path / "sub" / "book.epub"
    book.parent.mkdir()
    tab.file_list.add_files([book])
    assert tab.output_dir.get() == str(book.parent)


def test_kfx_init_prefills_from_config(qtbot: QtBot) -> None:
    """Zapamiętany katalog z configu jest podpowiadany na starcie."""
    tab = KfxTab(tools=_tools(), config={"last_output_dir": "/remembered"})
    qtbot.addWidget(tab)
    assert tab.output_dir.get() == "/remembered"


def test_kfx_run_button_starts_worker(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_worker: type
) -> None:
    """Klik startuje workera KFX z plikami, katalogiem i KfxOptions; pamięta katalog."""
    monkeypatch.setattr(kfx_module, "Worker", fake_worker)
    config: dict = {}
    tab = KfxTab(tools=_tools(), config=config)
    qtbot.addWidget(tab)

    book = tmp_path / "book.epub"
    output = tmp_path / "out"
    tab.file_list.add_files([book])
    tab.output_dir.set(str(output))
    tab._run_conversion()

    assert config["last_output_dir"] == str(output)
    fn, args, _kwargs = fake_worker.captured[-1]  # type: ignore[attr-defined]
    assert fn is _run_kfx_worker
    assert args[0] == [book]
    assert args[1] == output
    assert isinstance(args[2], KfxOptions)


def test_kfx_empty_output_passes_none(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_worker: type
) -> None:
    """Puste pole katalogu → worker dostaje None (zapis obok źródła)."""
    monkeypatch.setattr(kfx_module, "Worker", fake_worker)
    tab = KfxTab(tools=_tools())
    qtbot.addWidget(tab)
    tab.file_list.add_files([tmp_path / "book.epub"])
    tab.output_dir.set("")
    tab._run_conversion()

    _fn, args, _kwargs = fake_worker.captured[-1]  # type: ignore[attr-defined]
    assert args[1] is None


def test_run_kfx_worker_calls_to_kfx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Funkcja robocza woła strumieniowy to_kfx dla każdego pliku i liczy sukcesy."""
    calls: list[tuple[Path, Path, KfxOptions]] = []

    def fake_to_kfx_streaming(
        source: Path,
        target_dir: Path,
        options: KfxOptions,
        *,
        on_line: object,
        on_progress: object = None,
        should_cancel: object = None,
    ) -> ConversionResult:
        calls.append((source, target_dir, options))
        return ConversionResult(True, target_dir / f"{source.stem}.kfx", "", "calibre")

    monkeypatch.setattr(kfx_module, "to_kfx_streaming", fake_to_kfx_streaming)
    book = tmp_path / "book.epub"
    output = tmp_path / "out"
    options = KfxOptions(engine="calibre", fix_epub_first=True)

    succeeded, total = _run_kfx_worker(
        lambda text, level: None, lambda c, t: None, lambda: False, [book], output, options
    )
    assert (succeeded, total) == (1, 1)
    assert calls == [(book, output, options)]


def test_run_mobi_worker_calls_to_mobi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Funkcja robocza MOBI woła strumieniowy to_mobi z celem o właściwym rozszerzeniu."""
    calls: list[tuple[Path, Path, MobiOptions]] = []

    def fake_to_mobi_streaming(
        source: Path,
        target: Path,
        options: MobiOptions,
        *,
        on_line: object,
        on_progress: object = None,
        should_cancel: object = None,
    ) -> ConversionResult:
        calls.append((source, target, options))
        return ConversionResult(True, target, "", "calibre")

    monkeypatch.setattr(kfx_module, "to_mobi_streaming", fake_to_mobi_streaming)
    book = tmp_path / "book.epub"
    output = tmp_path / "out"
    options = MobiOptions(fmt="azw3", engine="calibre", fix_epub_first=True)

    succeeded, total = _run_mobi_worker(
        lambda text, level: None, lambda c, t: None, lambda: False, [book], output, options
    )
    assert (succeeded, total) == (1, 1)
    source, target, opts = calls[0]
    assert source == book
    assert target == output / "book.azw3"
    assert opts.fmt == "azw3"
