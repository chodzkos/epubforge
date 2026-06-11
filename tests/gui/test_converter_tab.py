"""Testy zakładki GUI konwersji do EPUB (PySide6)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from epubforge.converters import ConversionResult, ConvertOptions
from epubforge.gui.tabs import converter as converter_module
from epubforge.gui.tabs.converter import ConverterTab, _run_conversion

pytestmark = pytest.mark.gui


def _emit_sink() -> tuple[list[tuple[str, str]], list[tuple[int, int]]]:
    return [], []


def test_converter_lists_only_supported_inputs(qtbot: QtBot, tmp_path: Path) -> None:
    """Zakładka przyjmuje obsługiwane formaty wejściowe, a EPUB pomija."""
    tab = ConverterTab()
    qtbot.addWidget(tab)
    txt = tmp_path / "a.txt"
    epub = tmp_path / "b.epub"
    tab.file_list.add_files([txt, epub])

    assert tab.file_list.files() == [txt]


def test_converter_pdf_requires_confirmation(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PDF dodaje się dopiero po potwierdzeniu w QMessageBox."""
    tab = ConverterTab()
    qtbot.addWidget(tab)
    pdf = tmp_path / "doc.pdf"

    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
    )
    tab.file_list.add_files([pdf])
    assert tab.file_list.files() == []

    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    tab.file_list.add_files([pdf])
    assert tab.file_list.files() == [pdf]


def test_converter_builds_options_from_form(qtbot: QtBot) -> None:
    """Formularz składa ConvertOptions z tytułem, autorem i językiem."""
    tab = ConverterTab()
    qtbot.addWidget(tab)
    tab.title_edit.setText("Mój Tytuł")
    tab.author_edit.setText("Jan Kowalski")
    tab.language_box.setCurrentText("pl")

    options = tab._build_convert_options()
    assert options.metadata is not None
    assert options.metadata.title == "Mój Tytuł"
    assert options.metadata.creators == ["Jan Kowalski"]
    assert options.metadata.language == "pl"


def test_converter_prefills_output_from_first_file(qtbot: QtBot, tmp_path: Path) -> None:
    """Dodanie pierwszego pliku przy pustym polu podpowiada jego katalog."""
    tab = ConverterTab()
    qtbot.addWidget(tab)
    book = tmp_path / "sub" / "in.txt"
    book.parent.mkdir()
    tab.file_list.add_files([book])
    assert tab.output_entry.get() == str(book.parent)


def test_converter_respects_manual_output(qtbot: QtBot, tmp_path: Path) -> None:
    """Ręcznie ustawiony katalog nie jest nadpisywany przy dodaniu pliku."""
    tab = ConverterTab()
    qtbot.addWidget(tab)
    tab.output_entry.set("/custom/out")
    tab.file_list.add_files([tmp_path / "in.txt"])
    assert tab.output_entry.get() == "/custom/out"


def test_converter_init_prefills_from_config(qtbot: QtBot) -> None:
    """Zapamiętany katalog z configu jest podpowiadany na starcie."""
    tab = ConverterTab(config={"last_output_dir": "/remembered"})
    qtbot.addWidget(tab)
    assert tab.output_entry.get() == "/remembered"


def test_converter_convert_remembers_output(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_worker: type
) -> None:
    """Uruchomienie konwersji zapamiętuje katalog i startuje workera z plikami."""
    monkeypatch.setattr(converter_module, "Worker", fake_worker)
    config: dict = {}
    tab = ConverterTab(config=config)
    qtbot.addWidget(tab)

    book = tmp_path / "a.txt"
    tab.file_list.add_files([book])
    tab.output_entry.set(str(tmp_path))
    tab._convert()

    assert config["last_output_dir"] == str(tmp_path)
    fn, args, _kwargs = fake_worker.captured[-1]  # type: ignore[attr-defined]
    assert fn is _run_conversion
    assert args[0] == [book]
    assert args[1] == tmp_path


def test_run_conversion_worker_calls_to_epub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Funkcja robocza woła to_epub dla każdego pliku i liczy sukcesy."""
    calls: list[tuple[Path, Path, ConvertOptions, str]] = []

    def fake_to_epub(
        source: Path,
        target: Path,
        options: ConvertOptions | None = None,
        engine: str = "auto",
    ) -> ConversionResult:
        assert options is not None
        calls.append((source, target, options, engine))
        return ConversionResult(success=True, output_path=target, log="gotowe", engine="pandoc")

    monkeypatch.setattr(converter_module, "to_epub", fake_to_epub)
    lines, _progress = _emit_sink()
    src = tmp_path / "in.txt"
    options = ConvertOptions()

    succeeded, total = _run_conversion(
        lambda text, level: lines.append((text, level)),
        lambda current, total_: None,
        [src],
        tmp_path,
        options,
        "auto",
    )

    assert (succeeded, total) == (1, 1)
    source, target, _opts, engine = calls[0]
    assert source == src
    assert target == tmp_path / "in.epub"
    assert engine == "auto"


def test_run_conversion_none_output_uses_source_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brak katalogu (None) → konwersja zapisuje obok pliku źródłowego."""
    targets: list[Path] = []

    def fake_to_epub(
        source: Path,
        target: Path,
        options: ConvertOptions | None = None,
        engine: str = "auto",
    ) -> ConversionResult:
        targets.append(target)
        return ConversionResult(success=True, output_path=target, log="", engine="pandoc")

    monkeypatch.setattr(converter_module, "to_epub", fake_to_epub)
    src = tmp_path / "sub" / "book.txt"
    src.parent.mkdir()

    _run_conversion(
        lambda text, level: None, lambda c, t: None, [src], None, ConvertOptions(), "auto"
    )
    assert targets == [src.parent / "book.epub"]
