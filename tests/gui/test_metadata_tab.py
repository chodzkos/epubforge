"""Testy zakładki GUI do edycji metadanych (PySide6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest
from lxml import etree
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from epubforge.core import Metadata, Tool, get_number_of_pages
from epubforge.gui.tabs import metadata as metadata_module
from epubforge.gui.tabs.metadata import MetadataTab

pytestmark = pytest.mark.gui


class FakeEpub:
    """Mały fake tylko dla GUI; API zgodne z używanym fragmentem Epub."""

    saved_metadata: ClassVar[Metadata | None] = None
    opened_paths: ClassVar[list[Path]] = []
    written_opf: ClassVar[bytes | None] = None
    save_calls: ClassVar[int] = 0
    source_opf: ClassVar[bytes] = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Stary tytuł</dc:title>
    <dc:creator>Autor A</dc:creator><dc:creator>Autor B</dc:creator>
    <dc:language>pl</dc:language><dc:identifier>9780000000000</dc:identifier>
    <dc:publisher>Wydawca</dc:publisher><dc:date>2026-06-10</dc:date>
    <dc:description>Opis książki</dc:description>
    <dc:subject>temat</dc:subject><dc:subject>epub</dc:subject>
    <meta name="calibre:series" content="Wiedźmin"/>
    <meta name="calibre:series_index" content="2"/>
    <meta property="schema:numberOfPages">321</meta>
  </metadata>
  <manifest><item id="c" href="c.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="c"/></spine>
</package>""".encode()

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.opened_paths.append(self.path)

    def __enter__(self) -> FakeEpub:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    @property
    def opf_path(self) -> str:
        return "OEBPS/content.opf"

    @property
    def metadata(self) -> Metadata:
        return Metadata.from_opf(self.read_file(self.opf_path))

    def read_file(self, _path: str) -> bytes:
        return FakeEpub.written_opf or FakeEpub.source_opf

    def write_file(self, _path: str, data: bytes) -> None:
        FakeEpub.written_opf = data
        FakeEpub.saved_metadata = Metadata.from_opf(data)

    def save(self) -> None:
        FakeEpub.save_calls += 1


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
    """Zakładka ładuje formularz i zapisuje jeden spójny OPF."""
    monkeypatch.setattr(metadata_module, "Epub", FakeEpub)
    FakeEpub.saved_metadata = None
    FakeEpub.opened_paths = []
    FakeEpub.written_opf = None
    FakeEpub.save_calls = 0

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
    assert tab.pages.value() == 321

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
    assert FakeEpub.save_calls == 1


def test_metadata_invalid_series_index_does_not_block_save(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Niepoprawny numer tomu ostrzega, ale zapisuje pozostałe pola."""
    warnings: list[str] = []
    monkeypatch.setattr(metadata_module, "Epub", FakeEpub)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a[2])))
    FakeEpub.saved_metadata = None
    FakeEpub.opened_paths = []
    FakeEpub.written_opf = None
    FakeEpub.save_calls = 0

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


def test_page_count_can_be_overwritten_and_cleared(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ręczna wartość nadpisuje istniejącą, a „—” usuwa ją przy jednym zapisie."""
    monkeypatch.setattr(metadata_module, "Epub", FakeEpub)
    FakeEpub.written_opf = None
    FakeEpub.save_calls = 0
    tab = MetadataTab(tools=_tools())
    qtbot.addWidget(tab)
    book = tmp_path / "book.epub"
    book.write_bytes(b"epub")
    tab._load_metadata(book)

    tab.pages.page_count.setValue(456)
    tab._save_metadata()
    assert FakeEpub.written_opf is not None
    assert get_number_of_pages(FakeEpub.written_opf) == 456
    assert FakeEpub.save_calls == 1

    FakeEpub.save_calls = 0
    tab.pages.page_count.setValue(0)
    tab._save_metadata()
    assert FakeEpub.written_opf is not None
    assert get_number_of_pages(FakeEpub.written_opf) is None
    assert FakeEpub.save_calls == 1


def test_epub2_disables_pages_and_keeps_opf_structures(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EPUB 2 blokuje strony, a zapis zachowuje manifest, spine i obce meta."""
    epub2 = FakeEpub.source_opf.replace(b'version="3.0"', b'version="2.0"').replace(
        b'<meta property="schema:numberOfPages">321</meta>',
        b'<meta name="foreign:key" content="keep"/>',
    )
    monkeypatch.setattr(metadata_module, "Epub", FakeEpub)
    monkeypatch.setattr(FakeEpub, "source_opf", epub2)
    FakeEpub.written_opf = None
    FakeEpub.save_calls = 0
    tab = MetadataTab(tools=_tools())
    qtbot.addWidget(tab)
    book = tmp_path / "book2.epub"
    book.write_bytes(b"epub")
    tab._load_metadata(book)

    assert not tab.pages.page_count.isEnabled()
    assert not tab.pages.calculate_button.isEnabled()
    assert not tab.pages.epub2_notice.isHidden()
    tab.title_edit.setText("Nowy tytuł EPUB 2")
    tab._save_metadata()

    assert FakeEpub.written_opf is not None
    source_root = etree.fromstring(epub2)
    root = etree.fromstring(FakeEpub.written_opf)
    source_manifest = source_root.find("{http://www.idpf.org/2007/opf}manifest")
    source_spine = source_root.find("{http://www.idpf.org/2007/opf}spine")
    manifest = root.find("{http://www.idpf.org/2007/opf}manifest")
    spine = root.find("{http://www.idpf.org/2007/opf}spine")
    assert source_manifest is not None and manifest is not None
    assert source_spine is not None and spine is not None
    assert etree.tostring(manifest) == etree.tostring(source_manifest)
    assert etree.tostring(spine) == etree.tostring(source_spine)
    foreign = root.find(".//{http://www.idpf.org/2007/opf}meta[@name='foreign:key']")
    assert foreign is not None
    assert FakeEpub.save_calls == 1


def test_metadata_external_tool_buttons(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Niedostępny edytor jest wyłączony, dostępny dostaje ścieżkę EPUB."""
    calls: list[list[str]] = []

    def fake_popen(cmd: list[str], **kwargs: Any) -> object:
        calls.append(cmd)
        return object()

    monkeypatch.setattr("epubforge.gui.external_tools.subprocess.Popen", fake_popen)

    tab = MetadataTab(tools=_tools())
    qtbot.addWidget(tab)
    book = tmp_path / "book.epub"
    tab.current_path = book

    assert tab.tool_buttons["calibre_editor"].isEnabled() is False
    assert tab.tool_buttons["sigil"].isEnabled() is True

    tab._open_external("sigil", "Sigil")
    assert calls[0] == [str(Path("/bin/sigil")), str(book)]
