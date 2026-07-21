"""Responsywny, poziomo przewijany pasek kontrolek zgodny z gui-kit."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QWidget,
)


class HorizontalStrip(QScrollArea):
    """Chroni pełne etykiety kontrolek przed ściskaniem i ucinaniem.

    Pasek ma mały minimalny rozmiar poziomy, więc nie odbiera szerokości edytorowi
    wewnątrz splittera. Gdy wszystkie kontrolki się nie mieszczą, pozostają w
    naturalnym rozmiarze i pojawia się przewijanie poziome.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.content = QWidget()
        self.row = QHBoxLayout(self.content)
        self.row.setContentsMargins(0, 0, 0, 0)
        _configure_scroll(self, self.content)

    def finish(self) -> None:
        """Utrwala naturalną szerokość i wysokość po dodaniu kontrolek."""
        _finish_scroll(self, self.content)


def make_horizontal_panel(content: QWidget) -> QScrollArea:
    """Owija dowolny szeroki panel przewijaniem bez propagowania jego szerokości."""
    scroll = QScrollArea()
    _configure_scroll(scroll, content)
    _finish_scroll(scroll, content)
    return scroll


def _configure_scroll(scroll: QScrollArea, content: QWidget) -> None:
    """Wspólna konfiguracja poziomego scrolla bez kolorów ani lokalnego QSS."""
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidgetResizable(True)
    scroll.setWidget(content)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


def _finish_scroll(scroll: QScrollArea, content: QWidget) -> None:
    """Oblicza geometrię dopiero po zbudowaniu zawartości."""
    hint = content.sizeHint()
    content.setMinimumWidth(hint.width())
    bar_height = scroll.horizontalScrollBar().sizeHint().height()
    scroll.setFixedHeight(hint.height() + bar_height)
