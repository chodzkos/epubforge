"""Testy własnego silnika motywu (Fusion + QPalette + QSS akcenty)."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QToolTip

from epubforge.gui import theme as theme_mod
from epubforge.gui.theme import (
    DARK,
    LIGHT,
    PRIMARY,
    Theme,
    ThemeManager,
    _build_qss,
    apply_theme,
    current_theme,
)

pytestmark = pytest.mark.gui


def test_brand_accent_is_marketing_green() -> None:
    """Akcent marki to #5DCAA5 (GUI_STANDARD §5)."""
    assert PRIMARY == "#5DCAA5"
    assert DARK.accent == "#5DCAA5"


def test_apply_dark_sets_fusion_palette_and_states(qapp: QApplication) -> None:
    """Ciemny: styl Fusion, role bazowe i grupa Disabled wg §5."""
    config: dict[str, object] = {}
    manager = ThemeManager(qapp, config)

    emitted: list[object] = []
    manager.theme_changed.connect(emitted.append)
    manager.apply("dark")

    # Po setStyleSheet styl jest opakowany w QStyleSheetStyle — czyszcząc QSS
    # odsłaniamy styl bazowy, który MUSI być Fusion (§4).
    palette = qapp.palette()
    qapp.setStyleSheet("")
    assert "fusion" in qapp.style().metaObject().className().lower()
    role = QPalette.ColorRole
    group = QPalette.ColorGroup
    # QColor.name() zwraca hex małymi literami — porównujemy bez wielkości liter.
    assert palette.color(role.Window).name() == DARK.bg.lower()
    assert palette.color(role.Base).name() == DARK.bg3.lower()
    assert palette.color(role.Highlight).name() == DARK.accent2.lower()
    assert palette.color(role.PlaceholderText).name() == DARK.fg3.lower()
    assert palette.color(group.Disabled, role.WindowText).name() == DARK.disabled_fg.lower()
    assert palette.color(role.Link).name() == DARK.accent.lower()

    assert manager.setting == "dark"
    assert manager.theme == DARK
    assert config["theme"] == "dark"
    assert current_theme() == DARK
    assert emitted == [DARK]


def test_apply_light_link_meets_wcag(qapp: QApplication) -> None:
    """Jasny: tło białe, a link to ciemniejszy accent2 #0F7C5B (nota WCAG §5)."""
    manager = ThemeManager(qapp, {})
    manager.apply("light")

    palette = qapp.palette()
    role = QPalette.ColorRole
    assert palette.color(role.Window).name() == "#ffffff"
    assert palette.color(role.Link).name() == "#0f7c5b"
    assert manager.theme == LIGHT
    assert current_theme() == LIGHT


@pytest.mark.parametrize("theme", [DARK, LIGHT])
def test_qss_has_no_base_palette_hexes(theme: Theme) -> None:
    """QSS niesie tylko akcenty — kolorów bazowych z palety w nim nie ma (§4)."""
    qss = _build_qss(theme)
    for hex_value in (theme.bg, theme.bg2, theme.bg3, theme.fg, theme.fg2, theme.fg3):
        assert hex_value not in qss, f"QSS dubluje kolor bazowy {hex_value}"


def test_system_scheme_maps_unknown_to_dark(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """system_scheme: Light→light, Dark/Unknown→dark (fallback dla Linux bez XDG)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    class _FakeHints:
        def __init__(self, scheme: Qt.ColorScheme) -> None:
            self._scheme = scheme

        def colorScheme(self) -> Qt.ColorScheme:  # noqa: N802 — Qt API
            return self._scheme

    for scheme, expected in (
        (Qt.ColorScheme.Light, "light"),
        (Qt.ColorScheme.Dark, "dark"),
        (Qt.ColorScheme.Unknown, "dark"),
    ):
        monkeypatch.setattr(
            QGuiApplication, "styleHints", staticmethod(lambda s=scheme: _FakeHints(s))
        )
        assert theme_mod.system_scheme() == expected


def test_auto_maps_system_scheme(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tryb auto rozwiązuje motyw z motywu systemu (Dark/Light)."""
    manager = ThemeManager(qapp, {})
    monkeypatch.setattr(theme_mod, "system_scheme", lambda: "dark")
    assert manager.resolved_name("auto") == "dark"
    monkeypatch.setattr(theme_mod, "system_scheme", lambda: "light")
    assert manager.resolved_name("auto") == "light"


def test_colorscheme_subscription_only_in_auto(qapp: QApplication) -> None:
    """colorSchemeChanged podłączony tylko w trybie auto, odłączany przy wymuszeniu."""
    manager = ThemeManager(qapp, {})
    manager.apply("auto")
    assert manager._auto_connection is not None
    manager.apply("dark")
    assert manager._auto_connection is None
    manager.apply("auto")
    assert manager._auto_connection is not None


def test_initial_setting_read_from_config(qapp: QApplication) -> None:
    """Ustawienie startowe pochodzi z configu (domyślnie auto przy złej wartości)."""
    assert ThemeManager(qapp, {"theme": "dark"}).setting == "dark"
    assert ThemeManager(qapp, {"theme": "śmieci"}).setting == "auto"
    assert ThemeManager(qapp, {}).setting == "auto"


def test_apply_theme_repolishes_without_error(qapp: QApplication) -> None:
    """apply_theme stosuje motyw bez wyjątku (Fusion + paleta + QSS + repolish)."""
    apply_theme(qapp, LIGHT)
    assert qapp.styleSheet() != ""
    apply_theme(qapp, DARK)
    assert qapp.styleSheet() != ""
    qapp.setStyleSheet("")  # odsłoń styl bazowy
    assert "fusion" in qapp.style().metaObject().className().lower()


def test_tooltip_palette_and_qss_refresh_on_runtime_theme_switch(qapp: QApplication) -> None:
    """Tooltip i QSS dostają świeże kolory przy zmianie motywu w locie."""
    manager = ThemeManager(qapp, {})
    role = QPalette.ColorRole

    manager.apply("dark")
    assert QToolTip.palette().color(role.ToolTipBase).name() == DARK.bg2.lower()
    assert QToolTip.palette().color(role.ToolTipText).name() == DARK.fg.lower()

    manager.apply("light")
    light_qss = qapp.styleSheet().lower()
    assert QToolTip.palette().color(role.ToolTipBase).name() == LIGHT.bg2.lower()
    assert QToolTip.palette().color(role.ToolTipText).name() == LIGHT.fg.lower()
    assert DARK.bg2.lower() not in light_qss
    assert DARK.fg.lower() not in light_qss

    manager.apply("dark")
    dark_qss = qapp.styleSheet().lower()
    assert QToolTip.palette().color(role.ToolTipBase).name() == DARK.bg2.lower()
    assert QToolTip.palette().color(role.ToolTipText).name() == DARK.fg.lower()
    assert LIGHT.bg2.lower() not in dark_qss
    assert LIGHT.fg.lower() not in dark_qss
