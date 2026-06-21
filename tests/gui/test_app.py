"""Testy głównego okna aplikacji (PySide6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from chodzkos_gui_kit.qt.theme import ThemeManager
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from epubforge.core import Tool
from epubforge.core.config import ConfigStore
from epubforge.gui.app import MainWindow

pytestmark = pytest.mark.gui


def _make_window(qtbot: QtBot, qapp: QApplication, tmp_path: Path, config: dict) -> MainWindow:
    config_path = tmp_path / "config.json"
    store = ConfigStore("epubforge", path=config_path)
    store.update(config)  # seed in-memory (update omija __setitem__ → start „czysty")
    tools = {
        "pandoc": Tool("pandoc", None, available=False),
        "calibre_ebook_convert": Tool(
            "calibre_ebook_convert", Path("/bin/ebook-convert"), available=True
        ),
    }
    manager = ThemeManager(qapp, store)
    window = MainWindow(config_path, store, tools, manager)
    qtbot.addWidget(window)
    return window


def test_main_window_has_working_tabs(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> None:
    """Okno buduje zakładki robocze (About wyjęte do górnego paska)."""
    window = _make_window(qtbot, qapp, tmp_path, {})
    titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert titles == [
        "Metadane",
        "Konwerter",
        "Fixer",
        "Eksport Kindle",
        "Edytor",
        "Walidacja",
        "Spis treści",
        "Statystyki",
    ]


def test_main_window_status_shows_detected_tools(
    qtbot: QtBot, qapp: QApplication, tmp_path: Path
) -> None:
    """Pasek statusu pokazuje stan wykrytych narzędzi (trwały widget, nie message)."""
    window = _make_window(qtbot, qapp, tmp_path, {})
    status = window._tools_status_label.text()
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


def test_window_starts_in_both_themes(qtbot: QtBot, qapp: QApplication, tmp_path: Path) -> None:
    """Okno startuje i przełącza ciemny↔jasny bez wyjątku (smoke)."""
    window = _make_window(qtbot, qapp, tmp_path, {})
    for setting in ("dark", "light", "dark"):
        window.theme_manager.apply(setting)
        assert window.theme_manager.palette.name == setting


def test_config_flush_debounced_then_written(
    qtbot: QtBot, qapp: QApplication, tmp_path: Path
) -> None:
    """mark_dirty nie pisze od razu; ręczny flush zapisuje na dysk."""
    window = _make_window(qtbot, qapp, tmp_path, {})
    window.config_data["last_output_dir"] = "/x"
    # Debounce: zapis odroczony, plik jeszcze nie istnieje.
    assert not (tmp_path / "config.json").exists()
    window._flush_config()
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved["last_output_dir"] == "/x"


def test_tool_status_survives_theme_change(
    qtbot: QtBot, qapp: QApplication, tmp_path: Path
) -> None:
    """BUG 2: status narzędzi znikał po zmianie motywu (był temporary showMessage)."""
    window = _make_window(qtbot, qapp, tmp_path, {})
    before = window._tools_status_label.text()
    assert "Calibre: OK" in before

    window.theme_manager.apply("dark")
    window.theme_manager.apply("light")

    # Trwały widget — treść zachowana po przełączeniu motywu (nie odbudowana z zera).
    assert window._tools_status_label.text() == before


def test_resize_debounces_then_syncs_titlebar(
    qtbot: QtBot, qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BUG 1: resize uzbraja debounce, a po ustaniu syncuje belkę SAMEGO okna."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QResizeEvent

    import epubforge.gui.app as app_mod

    window = _make_window(qtbot, qapp, tmp_path, {})
    window.resizeEvent(QResizeEvent(QSize(820, 560), QSize(800, 540)))
    assert window._titlebar_resize_timer.isActive()  # debounce uzbrojony, nie sync co klatkę

    synced: list[tuple[object, str]] = []
    monkeypatch.setattr(app_mod, "sync_titlebar", lambda w, mode: synced.append((w, mode)))
    window._on_resize_settled()
    assert synced and synced[0][0] is window  # tylko główne okno, nie broadcast
