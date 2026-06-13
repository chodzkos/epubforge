"""Testy paska tytułu okna (DWM) — bezwarunkowe ustawianie (atrybut stanowy)."""

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


def test_sync_titlebar_sets_value_for_each_mode(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sync_titlebar ustawia DWM zgodnie z motywem aplikacji (dark→True, light→False)."""
    calls: list[bool] = []
    monkeypatch.setattr(window_theme, "set_titlebar_dark", lambda _w, dark: calls.append(dark))
    widget = QWidget()
    qtbot.addWidget(widget)

    window_theme.sync_titlebar(widget, "dark")
    window_theme.sync_titlebar(widget, "light")
    assert calls == [True, False]


def test_sync_titlebar_is_unconditional_stateful_regression(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """jasny→ciemny→jasny: ostatnie ustawienie to dark=False (regresja stanowości).

    Atrybut DWM jest stanowy — gdyby sync_titlebar pomijał ustawianie „bo motyw
    zgodny z systemem", końcowy jasny zostawiłby belkę ciemną.
    """
    calls: list[bool] = []
    monkeypatch.setattr(window_theme, "set_titlebar_dark", lambda _w, dark: calls.append(dark))
    widget = QWidget()
    qtbot.addWidget(widget)

    window_theme.sync_titlebar(widget, "light")
    window_theme.sync_titlebar(widget, "dark")
    window_theme.sync_titlebar(widget, "light")

    assert calls == [False, True, False]
    assert calls[-1] is False
