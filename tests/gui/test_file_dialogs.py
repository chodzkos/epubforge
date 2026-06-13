"""Testy helperów dialogów plików (natywny vs ciemny dialog Qt wg motywu)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QFileDialog, QToolButton
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
    """Gdy decyzja = Qt, helper buduje dialog i ustawia pasek tytułu na motyw app."""
    synced: list[str] = []
    monkeypatch.setattr(file_dialogs, "_native", lambda: False)
    monkeypatch.setattr(file_dialogs, "current_theme", lambda: _theme("dark"))
    monkeypatch.setattr(file_dialogs, "sync_titlebar", lambda _w, mode: synced.append(mode))
    monkeypatch.setattr(file_dialogs.QFileDialog, "exec", lambda self: 1)
    monkeypatch.setattr(file_dialogs.QFileDialog, "selectedFiles", lambda self: ["/a/book.epub"])

    result = file_dialogs.open_file(None, "Tytuł", "", "EPUB (*.epub)")

    assert result == "/a/book.epub"
    assert synced == ["dark"]


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


def test_dark_dialog_has_sidebar_and_detail_view(qtbot: QtBot) -> None:
    """Fallbackowy dialog Qt ma niepusty pasek boczny i widok szczegółowy."""
    dialog = file_dialogs._dark_dialog(None, "Tytuł", "", None)
    qtbot.addWidget(dialog)
    assert dialog.viewMode() == QFileDialog.ViewMode.Detail
    assert dialog.sidebarUrls()  # co najmniej dyski (QDir.drives)


def test_dark_dialog_restores_size_and_persists_on_run(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rozmiar okna jest odtwarzany z configu i zapisywany po zamknięciu dialogu."""
    config: dict[str, object] = {"file_dialog_size": [820, 600]}
    dialog = file_dialogs._dark_dialog(None, "Tytuł", "", config)
    qtbot.addWidget(dialog)
    assert (dialog.size().width(), dialog.size().height()) == (820, 600)

    dialog.resize(910, 540)
    monkeypatch.setattr(dialog, "exec", lambda: 0)  # anulowanie
    file_dialogs._first_selected(dialog, config)
    assert config["file_dialog_size"] == [910, 540]


def test_dark_dialog_toolbar_buttons_get_icon_and_unclipped(qtbot: QtBot) -> None:
    """Przyciski nawigacji dostają ikonę, a przycinający app-owy padding jest zdjęty.

    To była przyczyna „pustych przycisków" — w 22 px przycisku padding 4px 12px
    z app-QSS przycinał ikonę do zera. Labeling wołany tuż przed exec().
    """
    dialog = file_dialogs._dark_dialog(None, "Tytuł", "", None)
    qtbot.addWidget(dialog)
    file_dialogs._force_toolbar_buttons(dialog)  # w produkcji wołane tuż przed exec()
    for name in file_dialogs._NAV_ICONS:
        button = dialog.findChild(QToolButton, name)
        assert button is not None
        assert not button.icon().isNull()
        assert "padding: 1px" in button.styleSheet()  # ciężki padding zneutralizowany


def _theme(name: str) -> object:
    """Lekka atrapa motywu z polem ``name`` (helper bierze stąd app_mode)."""

    class _T:
        def __init__(self, n: str) -> None:
            self.name = n

    return _T(name)
