"""Testy zakładki GUI konwersji do EPUB (PySide6)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from epubforge.converters import ConversionResult, ConvertOptions
from epubforge.core import Tool
from epubforge.gui.tabs import converter as converter_module
from epubforge.gui.tabs.converter import ConverterTab, _run_conversion

pytestmark = pytest.mark.gui


def _emit_sink() -> tuple[list[tuple[str, str]], list[tuple[int, int]]]:
    return [], []


def _avail(name: str, path: str = "/bin/x") -> Tool:
    """Dostępne narzędzie do testów stanu UI."""
    return Tool(name, Path(path), version=f"{name} 1.0", available=True)


def _missing(name: str) -> Tool:
    """Niewykryte narzędzie do testów stanu UI."""
    return Tool(name, None, available=False)


def _no_pdf2md() -> dict[str, Tool]:
    """Zestaw narzędzi bez pdf2md (deterministyczny — bez realnej detekcji)."""
    return {"pdf2md": _missing("pdf2md"), "pdf2md_gui": _missing("pdf2md_gui")}


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
    """Bez pdf2md PDF dodaje się dopiero po potwierdzeniu w QMessageBox."""
    tab = ConverterTab(tools=_no_pdf2md())
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


def _click_dialog_button(monkeypatch: pytest.MonkeyPatch, index: int) -> None:
    """Symuluje kliknięcie przycisku dialogu wyboru silnika (0=pdf2md, 1=calibre, 2=anuluj)."""
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: self.buttons()[index])


def test_pdf_dialog_chooses_pdf2md(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Z wykrytym pdf2md dialog PDF pozwala wybrać pdf2md i zapamiętuje wybór."""
    config: dict = {}
    tab = ConverterTab(
        config=config, tools={"pdf2md": _avail("pdf2md"), "pdf2md_gui": _missing("pdf2md_gui")}
    )
    qtbot.addWidget(tab)
    _click_dialog_button(monkeypatch, 0)

    tab.file_list.add_files([tmp_path / "doc.pdf"])

    assert tab.file_list.files() == [tmp_path / "doc.pdf"]
    assert config["pdf_engine"] == "pdf2md"
    assert tab._engine_radios["pdf2md"].isChecked()
    assert tab._engine_radios["pdf2md"].isEnabled()


def test_pdf_dialog_chooses_calibre(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dialog PDF pozwala wybrać Calibre — plik przyjęty, wybór zapamiętany."""
    config: dict = {}
    tab = ConverterTab(
        config=config, tools={"pdf2md": _avail("pdf2md"), "pdf2md_gui": _missing("pdf2md_gui")}
    )
    qtbot.addWidget(tab)
    _click_dialog_button(monkeypatch, 1)

    tab.file_list.add_files([tmp_path / "doc.pdf"])

    assert tab.file_list.files() == [tmp_path / "doc.pdf"]
    assert config["pdf_engine"] == "calibre"
    assert tab._engine_radios["calibre"].isChecked()


def test_pdf_dialog_cancel_rejects_file(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anulowanie dialogu PDF odrzuca plik i nie zapisuje wyboru silnika."""
    config: dict = {}
    tab = ConverterTab(
        config=config, tools={"pdf2md": _avail("pdf2md"), "pdf2md_gui": _missing("pdf2md_gui")}
    )
    qtbot.addWidget(tab)
    _click_dialog_button(monkeypatch, 2)

    tab.file_list.add_files([tmp_path / "doc.pdf"])

    assert tab.file_list.files() == []
    assert "pdf_engine" not in config


def test_pdf2md_engine_state_follows_files(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Radio i handoff pdf2md włączają się dopiero, gdy na liście jest PDF."""
    tab = ConverterTab(tools={"pdf2md": _avail("pdf2md"), "pdf2md_gui": _avail("pdf2md_gui")})
    qtbot.addWidget(tab)
    # Bez plików: radio wyłączone, przycisk handoff widoczny (gui wykryte) lecz nieaktywny.
    assert tab._engine_radios["pdf2md"].isEnabled() is False
    assert tab.pdf2md_button.isHidden() is False
    assert tab.pdf2md_button.isEnabled() is False

    # Plik nie-PDF nie odblokowuje pdf2md.
    tab.file_list.add_files([tmp_path / "a.txt"])
    assert tab._engine_radios["pdf2md"].isEnabled() is False

    # Dodanie PDF (dialog → pdf2md) aktywuje radio i handoff.
    _click_dialog_button(monkeypatch, 0)
    tab.file_list.add_files([tmp_path / "b.pdf"])
    assert tab._engine_radios["pdf2md"].isEnabled() is True
    assert tab.pdf2md_button.isEnabled() is True


def test_open_in_pdf2md_launches_first_pdf(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Handoff uruchamia pdf2md-gui na pierwszym PDF-ie z listy."""
    tools = {"pdf2md": _missing("pdf2md"), "pdf2md_gui": _avail("pdf2md_gui", "/bin/pdf2md-gui")}
    tab = ConverterTab(tools=tools)
    qtbot.addWidget(tab)
    captured: dict = {}
    monkeypatch.setattr(
        converter_module,
        "launch_tool",
        lambda tool, target: captured.update(tool=tool, target=target),
    )
    # Bez pdf2md CLI dialog PDF idzie starą ścieżką „question" — potwierdź.
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    pdf = tmp_path / "doc.pdf"
    tab.file_list.add_files([tmp_path / "a.txt", pdf])

    tab._open_in_pdf2md()

    assert captured["target"] == pdf
    assert captured["tool"] is tools["pdf2md_gui"]


def test_open_in_pdf2md_without_pdf_sets_status(qtbot: QtBot) -> None:
    """Handoff bez PDF-a na liście nie uruchamia narzędzia, tylko informuje w statusie."""
    tab = ConverterTab(tools={"pdf2md": _missing("pdf2md"), "pdf2md_gui": _avail("pdf2md_gui")})
    qtbot.addWidget(tab)
    tab._open_in_pdf2md()
    assert "PDF" in tab.status_label.text()


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
    """Funkcja robocza woła strumieniowy to_epub dla każdego pliku i liczy sukcesy."""
    calls: list[tuple[Path, Path, ConvertOptions, str]] = []

    def fake_to_epub_streaming(
        source: Path,
        target: Path,
        options: ConvertOptions | None = None,
        engine: str = "auto",
        *,
        on_line: object,
        on_progress: object = None,
        should_cancel: object = None,
    ) -> ConversionResult:
        assert options is not None
        calls.append((source, target, options, engine))
        return ConversionResult(success=True, output_path=target, log="", engine="pandoc")

    monkeypatch.setattr(converter_module, "to_epub_streaming", fake_to_epub_streaming)
    lines, _progress = _emit_sink()
    src = tmp_path / "in.txt"
    options = ConvertOptions()

    succeeded, total = _run_conversion(
        lambda text, level: lines.append((text, level)),
        lambda current, total_: None,
        lambda: False,
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

    def fake_to_epub_streaming(
        source: Path,
        target: Path,
        options: ConvertOptions | None = None,
        engine: str = "auto",
        *,
        on_line: object,
        on_progress: object = None,
        should_cancel: object = None,
    ) -> ConversionResult:
        targets.append(target)
        return ConversionResult(success=True, output_path=target, log="", engine="pandoc")

    monkeypatch.setattr(converter_module, "to_epub_streaming", fake_to_epub_streaming)
    src = tmp_path / "sub" / "book.txt"
    src.parent.mkdir()

    _run_conversion(
        lambda text, level: None,
        lambda c, t: None,
        lambda: False,
        [src],
        None,
        ConvertOptions(),
        "auto",
    )
    assert targets == [src.parent / "book.epub"]


def test_run_conversion_stops_on_cancel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """should_cancel=True przerywa pętlę przed konwersją kolejnych plików."""
    calls: list[Path] = []

    def fake_to_epub_streaming(
        source: Path, target: Path, *a: object, **k: object
    ) -> ConversionResult:
        calls.append(source)
        return ConversionResult(success=True, output_path=target, log="", engine="pandoc")

    monkeypatch.setattr(converter_module, "to_epub_streaming", fake_to_epub_streaming)
    src = tmp_path / "in.txt"

    succeeded, total = _run_conversion(
        lambda text, level: None,
        lambda c, t: None,
        lambda: True,  # od razu anulowane
        [src],
        tmp_path,
        ConvertOptions(),
        "auto",
    )
    assert calls == []
    assert (succeeded, total) == (0, 1)
