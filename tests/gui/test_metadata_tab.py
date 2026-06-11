"""Testy zakładki GUI do edycji metadanych."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

if TYPE_CHECKING:
    import tkinter as tk
else:
    tk = pytest.importorskip("tkinter")

from epubforge.core import Metadata, Tool
from epubforge.gui.tabs import metadata as metadata_module
from epubforge.gui.tabs.metadata import MetadataTab

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


class FakeEpub:
    """Mały fake tylko dla GUI; API zgodne z używanym fragmentem Epub."""

    saved_metadata: ClassVar[Metadata | None] = None
    opened_paths: ClassVar[list[Path]] = []

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.opened_paths.append(self.path)

    def __enter__(self) -> FakeEpub:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    @property
    def metadata(self) -> Metadata:
        return Metadata(
            title="Stary tytuł",
            creators=["Autor A", "Autor B"],
            language="pl",
            identifier="9780000000000",
            publisher="Wydawca",
            date="2026-06-10",
            description="Opis książki",
            subjects=["temat", "epub"],
            series="Wiedźmin",
            series_index=2.0,
        )

    @metadata.setter
    def metadata(self, value: Metadata) -> None:
        FakeEpub.saved_metadata = value


def _tools() -> dict[str, Tool]:
    return {
        "sigil": Tool("sigil", Path("/bin/sigil"), available=True),
        "calibre_editor": Tool("calibre_editor", None, available=False),
        "calibre_viewer": Tool("calibre_viewer", Path("/bin/ebook-viewer"), available=True),
    }


def _saved_metadata() -> Metadata:
    metadata = FakeEpub.saved_metadata
    assert metadata is not None
    return metadata


def test_metadata_tab_loads_and_saves_metadata(
    root: tk.Tk,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zakładka tworzy się, ładuje metadane z Epub.metadata i zapisuje setterem."""
    monkeypatch.setattr(metadata_module, "Epub", FakeEpub)
    FakeEpub.saved_metadata = None
    FakeEpub.opened_paths = []

    tab = MetadataTab(root, tools=_tools())
    tab.pack(fill="both", expand=True)

    book = tmp_path / "book.epub"
    book.write_bytes(b"epub")
    tab.file_list.add_files([book])
    root.update_idletasks()

    assert tab.current_path == book
    assert tab.title_var.get() == "Stary tytuł"
    assert tab.series_var.get() == "Wiedźmin"
    assert tab.series_index_var.get() == "2"
    assert tab.language_var.get() == "pl"
    assert "Autor A" in tab.creators_text.get("1.0", "end-1c")
    assert "temat" in tab.subjects_text.get("1.0", "end-1c")

    tab.title_var.set("Nowy tytuł")
    tab.series_var.set("Saga o wiedźminie")
    tab.series_index_var.set("1.5")
    tab.creators_text.delete("1.0", "end")
    tab.creators_text.insert("1.0", "Nowy Autor\nDrugi Autor")
    tab.subjects_text.delete("1.0", "end")
    tab.subjects_text.insert("1.0", "nowe\nmetadane")
    tab._save_metadata()

    saved = _saved_metadata()
    assert saved.title == "Nowy tytuł"
    assert saved.series == "Saga o wiedźminie"
    assert saved.series_index == 1.5
    assert saved.creators == ["Nowy Autor", "Drugi Autor"]
    assert saved.subjects == ["nowe", "metadane"]
    assert FakeEpub.opened_paths[-1] == book


def test_metadata_tab_invalid_series_index_does_not_block_save(
    root: tk.Tk,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Niepoprawny numer tomu ostrzega, ale zapisuje pozostałe pola."""
    warnings: list[tuple[str, str]] = []

    monkeypatch.setattr(metadata_module, "Epub", FakeEpub)

    def fake_warning(title: str, message: str) -> None:
        warnings.append((title, message))

    monkeypatch.setattr("epubforge.gui.tabs.metadata.messagebox.showwarning", fake_warning)
    FakeEpub.saved_metadata = None
    FakeEpub.opened_paths = []

    tab = MetadataTab(root, tools=_tools())
    book = tmp_path / "book.epub"
    book.write_bytes(b"epub")
    tab.file_list.add_files([book])

    tab.title_var.set("Tytuł mimo błędu")
    tab.series_var.set("Nowy cykl")
    tab.series_index_var.set("drugi")
    tab._save_metadata()

    assert warnings
    saved = _saved_metadata()
    assert saved.title == "Tytuł mimo błędu"
    assert saved.series == "Nowy cykl"
    assert saved.series_index == 2.0


def test_metadata_tab_external_tool_buttons(
    root: tk.Tk,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Niedostępny edytor jest wyszarzony, a dostępny program dostaje ścieżkę EPUB."""
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_popen(cmd: list[str], **kwargs: Any) -> object:
        calls.append((cmd, kwargs))
        return object()

    monkeypatch.setattr("epubforge.gui.tabs.metadata.subprocess.Popen", fake_popen)

    tab = MetadataTab(root, tools=_tools())
    book = tmp_path / "book.epub"
    tab.current_path = book

    assert "disabled" in tab.tool_buttons["calibre_editor"].state()
    assert "disabled" not in tab.tool_buttons["sigil"].state()

    tab._open_external("sigil", "Sigil")
    assert calls[0][0] == ["/bin/sigil", str(book)]
