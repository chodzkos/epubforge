"""Helpery przewijalnych powierzchni zakładek."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QSizePolicy, QWidget


def make_scrollable(content: QWidget) -> QScrollArea:
    """Owija gotową zawartość zakładki w pionowy, bezramkowy ``QScrollArea``."""
    content.setAutoFillBackground(False)
    content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    area.setAcceptDrops(False)
    area.setAutoFillBackground(False)
    area.viewport().setAcceptDrops(False)
    area.viewport().setAutoFillBackground(False)
    area.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
    area.setWidget(content)
    return area
