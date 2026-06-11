"""Testy helperów dialogów plików (delegacja natywna vs ciemny dialog Qt)."""

from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from epubforge.gui import dialogs


def test_open_file_light_delegates_to_native(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """W trybie jasnym helper używa natywnego ``getOpenFileName``."""
    monkeypatch.setattr(dialogs, "native_file_dialogs", lambda: True)
    monkeypatch.setattr(
        dialogs.QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *a, **k: ("/x/book.epub", "")),
    )
    assert dialogs.open_file(None, "Tytuł", "", "EPUB (*.epub)") == "/x/book.epub"


def test_open_file_dark_darkens_titlebar_and_returns_selection(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W trybie ciemnym helper buduje dialog Qt i ciemni jego pasek tytułu."""
    darkened: list[bool] = []
    monkeypatch.setattr(dialogs, "native_file_dialogs", lambda: False)
    monkeypatch.setattr(
        dialogs, "set_titlebar_dark", lambda _w, dark: darkened.append(dark) is None
    )
    monkeypatch.setattr(dialogs.QFileDialog, "exec", lambda self: 1)
    monkeypatch.setattr(dialogs.QFileDialog, "selectedFiles", lambda self: ["/a/book.epub"])

    result = dialogs.open_file(None, "Tytuł", "", "EPUB (*.epub)")

    assert result == "/a/book.epub"
    assert darkened == [True]


def test_open_files_dark_cancelled_returns_empty(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anulowany ciemny dialog wielu plików zwraca pustą listę."""
    monkeypatch.setattr(dialogs, "native_file_dialogs", lambda: False)
    monkeypatch.setattr(dialogs, "set_titlebar_dark", lambda _w, _dark: True)
    monkeypatch.setattr(dialogs.QFileDialog, "exec", lambda self: 0)

    assert dialogs.open_files(None, "Dodaj pliki", "Obsługiwane (*.epub)") == []


def test_choose_directory_light_delegates_to_native(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W trybie jasnym wybór folderu używa natywnego dialogu."""
    monkeypatch.setattr(dialogs, "native_file_dialogs", lambda: True)
    monkeypatch.setattr(
        dialogs.QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *a, **k: "/home/books"),
    )
    assert dialogs.choose_directory(None, "Dodaj folder") == "/home/books"
