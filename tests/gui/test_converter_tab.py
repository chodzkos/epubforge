"""Testy zakładki GUI konwersji do EPUB."""

# ruff: noqa: E402

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")

from epubforge.converters import ConversionResult, ConvertOptions
from epubforge.gui.tabs import converter as converter_module
from epubforge.gui.tabs.converter import ConverterTab

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


def test_converter_tab_lists_only_supported_inputs(root: tk.Tk, tmp_path: Path) -> None:
    """Zakładka przyjmuje obsługiwane formaty wejściowe, a EPUB pomija."""
    tab = ConverterTab(root)
    tab.pack(fill="both", expand=True)

    txt = tmp_path / "a.txt"
    epub = tmp_path / "b.epub"
    tab.file_list.add_files([txt, epub])

    assert tab.file_list.files() == [txt]


def test_converter_pdf_requires_confirmation(
    root: tk.Tk,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PDF dodaje się dopiero po potwierdzeniu w askyesno."""
    tab = ConverterTab(root)
    pdf = tmp_path / "doc.pdf"

    monkeypatch.setattr(converter_module.messagebox, "askyesno", lambda *a, **k: False)
    tab.file_list.add_files([pdf])
    assert tab.file_list.files() == []

    monkeypatch.setattr(converter_module.messagebox, "askyesno", lambda *a, **k: True)
    tab.file_list.add_files([pdf])
    assert tab.file_list.files() == [pdf]


def test_converter_runs_conversion_per_file(
    root: tk.Tk,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker woła to_epub dla każdego pliku i przekazuje metadane z formularza."""
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

    tab = ConverterTab(root)
    tab.title_var.set("Mój Tytuł")
    tab.author_var.set("Jan Kowalski")
    tab.language_var.set("pl")

    src = tmp_path / "in.txt"
    options = tab._build_convert_options()
    tab._run_conversion([src], tmp_path, options, "auto")
    root.update()

    assert len(calls) == 1
    source, target, opts, engine = calls[0]
    assert source == src
    assert target == tmp_path / "in.epub"
    assert engine == "auto"
    assert opts.metadata is not None
    assert opts.metadata.title == "Mój Tytuł"
    assert opts.metadata.creators == ["Jan Kowalski"]
    assert opts.metadata.language == "pl"
    assert "Zakończono: 1/1 OK" in tab.status_var.get()
