"""Testy dialogu „Pobierz metadane…" i jego integracji z zakładką (PySide6).

Sieć jest w pełni zamockowana (``chain.fetch_by_isbn`` podmieniany), więc testy
nie wychodzą do żadnego API. Sprawdzamy: domyślne zaznaczenia (puste pola
formularza), listę deskryptorów (domyślnie odznaczone) oraz nanoszenie wyboru na
formularz zakładki wraz z liczbą stron zapisywaną przy zapisie.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest
from pytestqt.qtbot import QtBot

from epubforge.bookmeta import BookRecord
from epubforge.core import Metadata, Tool
from epubforge.gui.metadata_fetch import FetchMetadataDialog, FetchResult
from epubforge.gui.tabs import metadata as metadata_module
from epubforge.gui.tabs.metadata import MetadataTab

pytestmark = pytest.mark.gui

_RECORD = BookRecord(
    title="Ostatnie życzenie",
    creators=["Sapkowski, Andrzej"],
    publisher="SuperNOWA",
    date="2014",
    language="pl",
    page_count=330,
    subjects=["Fantasy", "Wiedźmin"],
    series="Wiedźmin",
    source="bn",
)


def _tools() -> dict[str, Tool]:
    return {
        "sigil": Tool("sigil", Path("/bin/sigil"), available=True),
        "calibre_editor": Tool("calibre_editor", None, available=False),
        "calibre_viewer": Tool("calibre_viewer", Path("/bin/ebook-viewer"), available=True),
    }


def _build_dialog(qtbot: QtBot, current: Metadata) -> FetchMetadataDialog:
    """Tworzy dialog i wypełnia go rekordem bez dotykania sieci."""
    dialog = FetchMetadataDialog(current, prefill_isbn="9788375780635")
    qtbot.addWidget(dialog)
    dialog._on_fetched(_RECORD)  # symulacja zakończenia workera
    return dialog


def test_dialog_defaults_check_only_empty_fields(qtbot: QtBot) -> None:
    """Pole skalarne jest domyślnie zaznaczone tylko gdy w formularzu jest puste."""
    current = Metadata(title="Mam tytuł")  # tytuł zajęty, reszta pusta
    dialog = _build_dialog(qtbot, current)

    title_box, _ = dialog._scalar_boxes["title"]
    publisher_box, _ = dialog._scalar_boxes["publisher"]
    assert title_box.isChecked() is False  # nie nadpisuj istniejącego
    assert publisher_box.isChecked() is True  # puste → domyślnie zaznaczone


def test_dialog_descriptors_default_unchecked(qtbot: QtBot) -> None:
    """Deskryptory BN są domyślnie ODznaczone (świadomy wybór użytkownika)."""
    dialog = _build_dialog(qtbot, Metadata())
    assert dialog._subject_boxes
    assert all(not box.isChecked() for box in dialog._subject_boxes)


def test_dialog_selection_collects_checked(qtbot: QtBot) -> None:
    """Zatwierdzenie zbiera zaznaczone pola, autorów, strony i deskryptory."""
    dialog = _build_dialog(qtbot, Metadata())
    dialog._subject_boxes[0].setChecked(True)  # zaznacz pierwszy deskryptor
    dialog._on_accept()

    selection = dialog.result_selection()
    assert selection.fields["title"] == "Ostatnie życzenie"
    assert selection.fields["publisher"] == "SuperNOWA"
    assert selection.creators == ["Sapkowski, Andrzej"]
    assert selection.page_count == 330
    assert selection.add_subjects == ["Fantasy"]


def test_dialog_no_result_shows_status(qtbot: QtBot) -> None:
    """Brak wyniku (None) → komunikat, OK pozostaje wyłączony."""
    dialog = FetchMetadataDialog(Metadata(), prefill_isbn="")
    qtbot.addWidget(dialog)
    dialog._on_fetched(None)
    assert not dialog._ok_button().isEnabled()


# ── Integracja z zakładką ────────────────────────────────────────────────────────


class _FakeEpub:
    """Fake Epub rejestrujący zapis OPF (setter metadanych + liczba stron)."""

    saved_metadata: ClassVar[Metadata | None] = None
    written_opf: ClassVar[bytes | None] = None
    opf = "OEBPS/content.opf"
    # OPF EPUB 3 z sekcją metadata (dla set_number_of_pages).
    _OPF3 = (
        b'<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" '
        b'version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        b"</metadata></package>"
    )

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def __enter__(self) -> _FakeEpub:
        return self

    def __exit__(self, *_a: object) -> None:
        return None

    @property
    def opf_path(self) -> str:
        return self.opf

    @property
    def metadata(self) -> Metadata:
        return Metadata()

    @metadata.setter
    def metadata(self, value: Metadata) -> None:
        _FakeEpub.saved_metadata = value

    def read_file(self, _path: str) -> bytes:
        return _FakeEpub.written_opf or self._OPF3

    def write_file(self, _path: str, data: bytes) -> None:
        _FakeEpub.written_opf = data

    def save(self) -> None:
        return None


def test_tab_applies_fetch_and_writes_pages(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wybór z dialogu trafia na formularz, a liczba stron do OPF przy zapisie."""
    monkeypatch.setattr(metadata_module, "Epub", _FakeEpub)
    _FakeEpub.saved_metadata = None
    _FakeEpub.written_opf = None

    tab = MetadataTab(tools=_tools())
    qtbot.addWidget(tab)
    book = tmp_path / "book.epub"
    book.write_bytes(b"epub")
    tab.current_path = book

    selection = FetchResult(
        fields={"title": "Ostatnie życzenie", "publisher": "SuperNOWA"},
        creators=["Sapkowski, Andrzej"],
        add_subjects=["Fantasy"],
        page_count=330,
    )
    tab._apply_fetch_result(selection)
    assert tab.title_edit.text() == "Ostatnie życzenie"
    assert tab.publisher_edit.text() == "SuperNOWA"
    assert "Fantasy" in tab.subjects_edit.toPlainText()

    tab._save_metadata()
    assert _FakeEpub.saved_metadata is not None
    assert _FakeEpub.saved_metadata.title == "Ostatnie życzenie"
    assert _FakeEpub.written_opf is not None
    assert b"schema:numberOfPages" in _FakeEpub.written_opf
    assert b"330" in _FakeEpub.written_opf


def test_tab_open_fetch_dialog_prefills_isbn(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otwierając dialog, zakładka prefiluje ISBN z identyfikatora (jeśli to ISBN)."""
    captured: dict[str, str] = {}

    class _StubDialog:
        DialogCode = FetchMetadataDialog.DialogCode

        def __init__(self, current: Metadata, *, prefill_isbn: str, parent: object) -> None:
            captured["isbn"] = prefill_isbn

        def exec(self) -> int:
            return int(FetchMetadataDialog.DialogCode.Rejected)

    monkeypatch.setattr(metadata_module, "FetchMetadataDialog", _StubDialog)
    tab = MetadataTab(tools=_tools())
    qtbot.addWidget(tab)
    tab.identifier_edit.setText("978-83-7578-063-5")
    tab._open_fetch_dialog()
    assert captured["isbn"] == "9788375780635"
