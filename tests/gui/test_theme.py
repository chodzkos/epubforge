"""Testy menedżera motywu (auto/jasny/ciemny) i ról palety."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from epubforge.gui.theme import (
    DARK,
    LIGHT,
    PRIMARY,
    ThemeManager,
    current_theme,
    native_file_dialogs,
)

pytestmark = pytest.mark.gui


def test_brand_accent_is_marketing_green() -> None:
    """Akcent marki to #5DCAA5 (GUI_STANDARD §5)."""
    assert PRIMARY == "#5DCAA5"
    assert DARK.accent == "#5DCAA5"


def test_apply_dark_sets_theme_and_persists(qapp: QApplication) -> None:
    """Tryb ciemny ustawia motyw DARK, zapisuje ustawienie i aktualizuje globals."""
    config: dict[str, object] = {}
    manager = ThemeManager(qapp, config)

    emitted: list[object] = []
    manager.theme_changed.connect(emitted.append)
    manager.apply("dark")

    assert manager.setting == "dark"
    assert manager.theme == DARK
    assert config["theme"] == "dark"
    assert current_theme() == DARK
    assert native_file_dialogs() is False
    assert emitted == [DARK]


def test_apply_light_uses_native_style_and_signal(qapp: QApplication) -> None:
    """Tryb jasny ustawia motyw LIGHT i pozwala na natywne dialogi plików."""
    config: dict[str, object] = {}
    manager = ThemeManager(qapp, config)
    manager.apply("light")

    assert manager.theme == LIGHT
    assert config["theme"] == "light"
    assert current_theme() == LIGHT
    assert native_file_dialogs() is True


def test_initial_setting_read_from_config(qapp: QApplication) -> None:
    """Ustawienie startowe pochodzi z configu (domyślnie auto przy złej wartości)."""
    assert ThemeManager(qapp, {"theme": "dark"}).setting == "dark"
    assert ThemeManager(qapp, {"theme": "śmieci"}).setting == "auto"
    assert ThemeManager(qapp, {}).setting == "auto"


def test_resolved_name_maps_auto_to_system(qapp: QApplication) -> None:
    """resolved_name mapuje jawne tryby wprost, a auto na motyw systemu."""
    manager = ThemeManager(qapp, {})
    assert manager.resolved_name("dark") == "dark"
    assert manager.resolved_name("light") == "light"
    assert manager.resolved_name("auto") in {"dark", "light"}


def test_titlebar_dark_is_noop_off_windows(qapp: QApplication) -> None:
    """Poza Windows ustawienie ciemnego paska tytułu jest bezpiecznym no-opem."""
    import sys

    from PySide6.QtWidgets import QWidget

    from epubforge.gui.window_theme import set_titlebar_dark

    widget = QWidget()
    result = set_titlebar_dark(widget, True)
    if sys.platform != "win32":
        assert result is False
