"""Podgląd obrazu rastrowego z EPUB — skalowanie z zachowaniem proporcji.

Trzyma oryginalny :class:`QPixmap` jako atrybut (inaczej GC by go zwolnił) i
przeskalowuje go do rozmiaru widgetu z debounce na ``resizeEvent`` (QTimer),
żeby przeciąganie krawędzi okna nie skalowało obrazu na każdą klatkę.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from epubforge.gui.resource_limits import RasterStatus, probe_raster
from epubforge.i18n import _

_RESIZE_DEBOUNCE_MS = 80


class ImagePreview(QWidget):
    """Wyświetla obraz wyśrodkowany, skalowany do rozmiaru widgetu (KeepAspectRatio)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None  # oryginał trzymany przy życiu (GC)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel(_("Brak podglądu"))
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(_RESIZE_DEBOUNCE_MS)
        self._resize_timer.timeout.connect(self._rescale)

    @property
    def message(self) -> str:
        """Bieżący tekst diagnostyczny podglądu obrazu."""
        return self._label.text()

    def show_data(self, data: bytes) -> bool:
        """Ładuje obraz z bajtów. Zwraca ``False``, gdy formatu nie da się wczytać."""
        probe = probe_raster(data)
        if probe.status is RasterStatus.TOO_LARGE:
            self._pixmap = None
            self._label.setText(_("Obraz jest zbyt duży do bezpiecznego podglądu."))
            return False
        if probe.status is RasterStatus.INVALID:
            self._pixmap = None
            self._label.setText(_("Nie udało się wczytać obrazu"))
            return False
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self._pixmap = None
            self._label.setText(_("Nie udało się wczytać obrazu"))
            return False
        self._pixmap = pixmap
        self._rescale()
        return True

    def _rescale(self) -> None:
        """Przeskalowuje oryginał do bieżącego rozmiaru widgetu."""
        if self._pixmap is None or self._pixmap.isNull():
            return
        self._label.setPixmap(
            self._pixmap.scaled(
                self._label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 — Qt API
        """Po zmianie rozmiaru przelicza skalę z debounce (nie na każdą klatkę)."""
        super().resizeEvent(event)
        self._resize_timer.start()
