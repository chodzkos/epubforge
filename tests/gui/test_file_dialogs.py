"""Testy helperów dialogów plików (natywny vs ciemny dialog Qt wg motywu)."""

from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from epubforge.gui import file_dialogs

pytestmark = pytest.mark.gui


@pytest.mark.parametrize(
    ("app_mode", "system", "expected_native"),
    [
        ("dark", "dark", True),  # zgodność → natywny
        ("light", "light", True),  # zgodność → natywny
        ("dark", "light", False),  # rozjazd → dialog Qt
        ("light", "dark", False),  # rozjazd (w obie strony) → dialog Qt
    ],
)
def test_use_native_dialog_symmetric_mismatch(
    app_mode: str, system: str, expected_native: bool
) -> None:
    """Natywny ⇔ motyw aplikacji == motyw systemu; przy KAŻDYM rozjeździe → Qt (§4)."""
    assert file_dialogs.use_native_dialog(app_mode, system) is expected_native  # type: ignore[arg-type]


def test_auto_mode_always_uses_native(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tryb auto: motyw aplikacji podąża za systemem → zgodność → zawsze natywny.

    Mockujemy motyw systemu (styleHints().colorScheme()) i NIE zmieniamy go w teście —
    sprawdzamy, że dla obu wartości systemu auto daje natywny dialog.
    """
    for system in ("dark", "light"):
        # W trybie auto efektywny motyw aplikacji == motyw systemu.
        monkeypatch.setattr(file_dialogs, "current_theme", lambda s=system: _theme(s))
        monkeypatch.setattr(file_dialogs, "system_scheme", lambda s=system: s)
        assert file_dialogs._native() is True


def test_open_file_native_delegates(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Gdy decyzja = natywny, helper używa ``getOpenFileName``."""
    monkeypatch.setattr(file_dialogs, "_native", lambda: True)
    monkeypatch.setattr(
        file_dialogs.QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *a, **k: ("/x/book.epub", "")),
    )
    assert file_dialogs.open_file(None, "Tytuł", "", "EPUB (*.epub)") == "/x/book.epub"


def test_open_file_qt_dialog_syncs_titlebar(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Gdy decyzja = Qt, helper buduje dialog i synchronizuje pasek tytułu."""
    synced: list[tuple[str, str]] = []
    monkeypatch.setattr(file_dialogs, "_native", lambda: False)
    monkeypatch.setattr(file_dialogs, "current_theme", lambda: _theme("dark"))
    monkeypatch.setattr(file_dialogs, "system_scheme", lambda: "light")
    monkeypatch.setattr(
        file_dialogs,
        "sync_titlebar",
        lambda _w, mode, system: synced.append((mode, system)),
    )
    monkeypatch.setattr(file_dialogs.QFileDialog, "exec", lambda self: 1)
    monkeypatch.setattr(file_dialogs.QFileDialog, "selectedFiles", lambda self: ["/a/book.epub"])

    result = file_dialogs.open_file(None, "Tytuł", "", "EPUB (*.epub)")

    assert result == "/a/book.epub"
    assert synced == [("dark", "light")]


def test_open_files_qt_cancelled_returns_empty(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anulowany dialog Qt wielu plików zwraca pustą listę."""
    monkeypatch.setattr(file_dialogs, "_native", lambda: False)
    monkeypatch.setattr(file_dialogs, "sync_titlebar", lambda *a, **k: None)
    monkeypatch.setattr(file_dialogs.QFileDialog, "exec", lambda self: 0)
    assert file_dialogs.open_files(None, "Dodaj pliki", "Obsługiwane (*.epub)") == []


def test_pick_dir_native_delegates(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Gdy decyzja = natywny, wybór folderu używa ``getExistingDirectory``."""
    monkeypatch.setattr(file_dialogs, "_native", lambda: True)
    monkeypatch.setattr(
        file_dialogs.QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *a, **k: "/home/books"),
    )
    assert file_dialogs.pick_dir(None, "Dodaj folder") == "/home/books"


def _theme(name: str) -> object:
    """Lekka atrapa motywu z polem ``name`` (helper bierze stąd app_mode)."""

    class _T:
        def __init__(self, n: str) -> None:
            self.name = n

    return _T(name)
