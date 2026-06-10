"""Testy zakładki GUI do edycji metadanych."""

# ruff: noqa: E402

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar

import pytest

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
    assert tab.language_var.get() == "pl"
    assert "Autor A" in tab.creators_text.get("1.0", "end-1c")
    assert "temat" in tab.subjects_text.get("1.0", "end-1c")

    tab.title_var.set("Nowy tytuł")
    tab.creators_text.delete("1.0", "end")
    tab.creators_text.insert("1.0", "Nowy Autor\nDrugi Autor")
    tab.subjects_text.delete("1.0", "end")
    tab.subjects_text.insert("1.0", "nowe\nmetadane")
    tab._save_metadata()

    assert FakeEpub.saved_metadata is not None
    assert FakeEpub.saved_metadata.title == "Nowy tytuł"
    assert FakeEpub.saved_metadata.creators == ["Nowy Autor", "Drugi Autor"]
    assert FakeEpub.saved_metadata.subjects == ["nowe", "metadane"]
    assert FakeEpub.opened_paths[-1] == book


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

    monkeypatch.setattr(metadata_module.subprocess, "Popen", fake_popen)

    tab = MetadataTab(root, tools=_tools())
    book = tmp_path / "book.epub"
    tab.current_path = book

    assert "disabled" in tab.tool_buttons["calibre_editor"].state()
    assert "disabled" not in tab.tool_buttons["sigil"].state()

    tab._open_external("sigil", "Sigil")
    assert calls[0][0] == ["/bin/sigil", str(book)]
