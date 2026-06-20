"""Smoke testy integracyjne: EpubForge poprawnie używa chodzkos-gui-kit.

Logika motywu/dialogów/titlebara/configu jest testowana w samym kicie (P1). Tu
sprawdzamy wyłącznie, że EpubForge spina się z kitem poprawnie: te same typy,
przepływ zmiany motywu w locie i decyzja natywny/nienatywny dialog.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from chodzkos_gui_kit.config import Config as KitConfig
from chodzkos_gui_kit.palette import Palette
from chodzkos_gui_kit.qt import dialogs
from chodzkos_gui_kit.qt.theme import ThemeManager, current_palette
from PySide6.QtWidgets import QApplication

from epubforge.core.config import ConfigStore

pytestmark = pytest.mark.gui


def test_config_store_is_kit_config_and_persists(tmp_path: Path) -> None:
    """``ConfigStore`` EpubForge to dokładnie ``chodzkos_gui_kit.config.Config``."""
    assert ConfigStore is KitConfig
    store = ConfigStore("epubforge", path=tmp_path / "config.json")
    store["theme"] = "dark"  # __setitem__ → dirty
    assert store.dirty is True
    store.flush()
    assert KitConfig("epubforge", path=tmp_path / "config.json").get("theme") == "dark"


def test_theme_switch_in_flight_updates_kit_current_palette(qapp: QApplication) -> None:
    """Zmiana motywu w locie przez kit aktualizuje current_palette() (czytane przez dialogi)."""
    emitted: list[object] = []
    manager = ThemeManager(qapp, {})
    manager.theme_changed.connect(emitted.append)

    manager.apply("dark")
    assert current_palette().name == "dark"
    manager.apply("light")
    assert current_palette().name == "light"

    # Sygnał niesie paletę kitu (a nie lokalny typ EpubForge).
    assert emitted and all(isinstance(p, Palette) for p in emitted)


def test_file_dialog_native_decision_delegates_to_kit() -> None:
    """Reguła rozjazdu (natywny ⇔ motyw app == system) pochodzi z kitu."""
    assert dialogs.use_native_dialog("dark", "dark") is True
    assert dialogs.use_native_dialog("light", "dark") is False
    # Helpery, których EpubForge używa w widgetach, są importowalne z kitu.
    assert callable(dialogs.open_file)
