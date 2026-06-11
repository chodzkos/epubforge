"""Testy głównego okna aplikacji (PySide6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from epubforge.core import Tool
from epubforge.gui.app import MainWindow
from epubforge.gui.theme import ThemeManager

pytestmark = pytest.mark.gui


def _make_window(qtbot: QtBot, qapp: QApplication, tmp_path: Path, config: dict) -> MainWindow:
    config_path = tmp_path / "config.json"
    tools = {
        "pandoc": Tool("pandoc", None, available=False),
        "calibre_ebook_convert": Tool(
            "calibre_ebook_convert", Path("/bin/ebook-convert"), available=True
        ),
    }
    manager = ThemeManager(qapp, config)
    window = MainWindow(config_path, config, tools, manager)
    qtbot.addWidget(window)
    return window


def test_main_window_has_four_working_tabs(
    qtbot: QtBot, qapp: QApplication, tmp_path: Path
) -> None:
    """Okno buduje 4 zakładki robocze (About wyjęte do górnego paska)."""
    window = _make_window(qtbot, qapp, tmp_path, {})
    titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert titles == ["Metadane", "Konwerter", "Fixer", "Eksport Kindle"]


def test_main_window_status_shows_detected_tools(
    qtbot: QtBot, qapp: QApplication, tmp_path: Path
) -> None:
    """Pasek statusu pokazuje stan wykrytych narzędzi."""
    window = _make_window(qtbot, qapp, tmp_path, {})
    status = window.statusBar().currentMessage()
    assert "Calibre: OK" in status
    assert "Pandoc: brak" in status


def test_theme_menu_switches_and_persists_on_close(
    qtbot: QtBot, qapp: QApplication, tmp_path: Path
) -> None:
    """Wybór motywu aktualizuje etykietę i zapisuje ustawienie przy zamknięciu."""
    config: dict = {}
    window = _make_window(qtbot, qapp, tmp_path, config)

    window._select_theme("light")
    assert "Jasny" in window.theme_button.text()
    assert window._theme_actions["light"].isChecked()  # type: ignore[attr-defined]

    window.close()
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["theme"] == "light"
    assert "window_geometry" in saved


def test_about_dialog_is_single_instance(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> None:
    """About otwiera pojedyncze okno i czyści referencję po zamknięciu."""
    window = _make_window(qtbot, qapp, tmp_path, {})

    window._open_about()
    first = window._about_dialog
    assert first is not None
    window._open_about()
    assert window._about_dialog is first

    first.reject()
    assert window._about_dialog is None


def test_geometry_restored_from_config(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> None:
    """Zapisana geometria z configu jest przywracana bez błędu."""
    window = _make_window(qtbot, qapp, tmp_path, {})
    window.resize(900, 640)
    window.close()
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))

    window2 = _make_window(qtbot, qapp, tmp_path, saved)
    assert isinstance(window2._about_dialog, type(None))
