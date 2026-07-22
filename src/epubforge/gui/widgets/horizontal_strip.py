"""Responsywny, poziomo przewijany pasek kontrolek zgodny z gui-kit."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QWidget,
)


class _NaturalWidthScrollArea(QScrollArea):
    """Przelicza naturalne rozmiary również po późnym zastosowaniu QSS gui-kit."""

    def __init__(self, content: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._content = content
        self._finished = False
        self._button_minimums: dict[QAbstractButton, int] = {}
        _configure_scroll(self, content)

    def finish(self) -> None:
        """Utrwala naturalną geometrię teraz i po zakończeniu bieżącej pętli zdarzeń."""
        self._finished = True
        self._refresh_natural_geometry()
        QTimer.singleShot(0, self._refresh_natural_geometry)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802 - API Qt
        """QSS gui-kit jest nakładany po budowie MainWindow, więc przelicz pasek ponownie."""
        super().changeEvent(event)
        if self._finished and event.type() in {
            QEvent.Type.StyleChange,
            QEvent.Type.FontChange,
            QEvent.Type.LanguageChange,
        }:
            QTimer.singleShot(0, self._refresh_natural_geometry)

    def _refresh_natural_geometry(self) -> None:
        """Nie pozwala layoutowi ścisnąć tekstu przycisku poniżej jego pełnego sizeHint."""
        for button in self._content.findChildren(QAbstractButton):
            baseline = self._button_minimums.setdefault(button, button.minimumWidth())
            button.setMinimumWidth(baseline)
            button.ensurePolished()
            button.setMinimumWidth(max(baseline, button.sizeHint().width()))
        _finish_scroll(self, self._content)


class HorizontalStrip(_NaturalWidthScrollArea):
    """Chroni pełne etykiety kontrolek przed ściskaniem i ucinaniem.

    Pasek ma mały minimalny rozmiar poziomy, więc nie odbiera szerokości edytorowi
    wewnątrz splittera. Gdy wszystkie kontrolki się nie mieszczą, pozostają w
    naturalnym rozmiarze i pojawia się przewijanie poziome.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        self.content = QWidget()
        self.row = QHBoxLayout(self.content)
        self.row.setContentsMargins(0, 0, 0, 0)
        super().__init__(self.content, parent)


def make_horizontal_panel(content: QWidget) -> QScrollArea:
    """Owija dowolny szeroki panel przewijaniem bez propagowania jego szerokości."""
    scroll = _NaturalWidthScrollArea(content)
    scroll.finish()
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
    layout = content.layout()
    if layout is not None:
        layout.invalidate()
        layout.activate()
    hint = content.sizeHint()
    content.setMinimumWidth(hint.width())
    bar_height = scroll.horizontalScrollBar().sizeHint().height()
    scroll.setFixedHeight(hint.height() + bar_height)
