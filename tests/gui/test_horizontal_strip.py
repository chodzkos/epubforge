"""Regresje responsywnych pasków kontrolek edytora."""

from __future__ import annotations

import pytest
from chodzkos_gui_kit.qt.theme import build_qss, current_palette
from PySide6.QtWidgets import QApplication, QPushButton
from pytestqt.qtbot import QtBot

from epubforge.gui.widgets.horizontal_strip import HorizontalStrip

pytestmark = pytest.mark.gui


def test_late_gui_kit_theme_keeps_long_editor_actions_unclipped(qtbot: QtBot) -> None:
    """QSS nakładany po budowie okna nie może ścisnąć trzech długich etykiet."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    previous_qss = app.styleSheet()
    strip = HorizontalStrip()
    buttons = [
        QPushButton("Ustawienia użytkownika"),
        QPushButton("Utwórz regułę dla elementu"),
        QPushButton("Podświetl wszystkie dopasowania"),
    ]
    for button in buttons:
        strip.row.addWidget(button)
    strip.finish()
    strip.setFixedWidth(240)
    qtbot.addWidget(strip)
    strip.show()

    try:
        app.setStyleSheet(build_qss(current_palette()))
        qtbot.waitUntil(lambda: strip.horizontalScrollBar().maximum() > 0)
        qtbot.waitUntil(
            lambda: all(button.minimumWidth() >= button.sizeHint().width() for button in buttons)
        )
        for button in buttons:
            assert button.width() >= button.sizeHint().width()
    finally:
        app.setStyleSheet(previous_qss)
