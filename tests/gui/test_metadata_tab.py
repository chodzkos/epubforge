"""Testy zakładki GUI do edycji metadanych (PySide6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from epubforge.core import Metadata, Tool
from epubforge.gui.tabs import metadata as metadata_module
from epubforge.gui.tabs.metadata import MetadataTab

pytestmark = pytest.mark.gui


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


def _saved() -> Metadata:
    assert FakeEpub.saved_metadata is not None
    return FakeEpub.saved_metadata


def test_metadata_loads_and_saves(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zakładka ładuje metadane z Epub.metadata i zapisuje setterem."""
    monkeypatch.setattr(metadata_module, "Epub", FakeEpub)
    FakeEpub.saved_metadata = None
    FakeEpub.opened_paths = []

    tab = MetadataTab(tools=_tools())
    qtbot.addWidget(tab)
    book = tmp_path / "book.epub"
    book.write_bytes(b"epub")
    tab.file_list.add_files([book])

    assert tab.current_path == book
    assert tab.title_edit.text() == "Stary tytuł"
    assert tab.series_edit.text() == "Wiedźmin"
    assert tab.series_index_edit.text() == "2"
    assert tab.language_edit.text() == "pl"
    assert "Autor A" in tab.creators_edit.toPlainText()
    assert "temat" in tab.subjects_edit.toPlainText()

    tab.title_edit.setText("Nowy tytuł")
    tab.series_edit.setText("Saga o wiedźminie")
    tab.series_index_edit.setText("1.5")
    tab.creators_edit.setPlainText("Nowy Autor\nDrugi Autor")
    tab.subjects_edit.setPlainText("nowe\nmetadane")
    tab._save_metadata()

    saved = _saved()
    assert saved.title == "Nowy tytuł"
    assert saved.series == "Saga o wiedźminie"
    assert saved.series_index == 1.5
    assert saved.creators == ["Nowy Autor", "Drugi Autor"]
    assert saved.subjects == ["nowe", "metadane"]
    assert FakeEpub.opened_paths[-1] == book


def test_metadata_invalid_series_index_does_not_block_save(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Niepoprawny numer tomu ostrzega, ale zapisuje pozostałe pola."""
    warnings: list[str] = []
    monkeypatch.setattr(metadata_module, "Epub", FakeEpub)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a[2])))
    FakeEpub.saved_metadata = None
    FakeEpub.opened_paths = []

    tab = MetadataTab(tools=_tools())
    qtbot.addWidget(tab)
    book = tmp_path / "book.epub"
    book.write_bytes(b"epub")
    tab.file_list.add_files([book])

    tab.title_edit.setText("Tytuł mimo błędu")
    tab.series_edit.setText("Nowy cykl")
    tab.series_index_edit.setText("drugi")
    tab._save_metadata()

    assert warnings
    saved = _saved()
    assert saved.title == "Tytuł mimo błędu"
    assert saved.series == "Nowy cykl"
    assert saved.series_index == 2.0


def test_metadata_external_tool_buttons(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Niedostępny edytor jest wyłączony, dostępny dostaje ścieżkę EPUB."""
    calls: list[list[str]] = []

    def fake_popen(cmd: list[str], **kwargs: Any) -> object:
        calls.append(cmd)
        return object()

    monkeypatch.setattr("epubforge.gui.tabs.metadata.subprocess.Popen", fake_popen)

    tab = MetadataTab(tools=_tools())
    qtbot.addWidget(tab)
    book = tmp_path / "book.epub"
    tab.current_path = book

    assert tab.tool_buttons["calibre_editor"].isEnabled() is False
    assert tab.tool_buttons["sigil"].isEnabled() is True

    tab._open_external("sigil", "Sigil")
    assert calls[0] == ["/bin/sigil", str(book)]
