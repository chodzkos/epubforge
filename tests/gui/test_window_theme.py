"""Testy paska tytułu okna (DWM) — synchronizacja tylko przy rozjeździe motywów."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from epubforge.gui import window_theme

pytestmark = pytest.mark.gui


def test_set_titlebar_dark_is_noop_off_windows(qtbot: QtBot) -> None:
    """Poza Windows ustawienie ciemnego paska tytułu jest bezpiecznym no-opem."""
    widget = QWidget()
    qtbot.addWidget(widget)
    result = window_theme.set_titlebar_dark(widget, True)
    if sys.platform != "win32":
        assert result is False


def test_sync_titlebar_skips_when_theme_matches_system(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gdy motyw aplikacji == motyw systemu, DWM nie jest dotykany (Qt 6.5+ sam prowadzi)."""
    calls: list[bool] = []
    monkeypatch.setattr(window_theme, "set_titlebar_dark", lambda _w, dark: calls.append(dark))
    widget = QWidget()
    qtbot.addWidget(widget)

    window_theme.sync_titlebar(widget, "dark", "dark")
    window_theme.sync_titlebar(widget, "light", "light")
    assert calls == []


def test_sync_titlebar_forces_dwm_on_mismatch(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Przy rozjeździe motyw≠system wymuszamy DWM zgodnie z motywem aplikacji."""
    calls: list[bool] = []
    monkeypatch.setattr(window_theme, "set_titlebar_dark", lambda _w, dark: calls.append(dark))
    widget = QWidget()
    qtbot.addWidget(widget)

    window_theme.sync_titlebar(widget, "dark", "light")
    window_theme.sync_titlebar(widget, "light", "dark")
    assert calls == [True, False]
