"""Pole liczby stron EPUB 3 i obliczanie estymacji poza wątkiem GUI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from epubforge.core import Epub
from epubforge.gui.workers import EmitLine, EmitProgress, Worker
from epubforge.i18n import _
from epubforge.stats import BookStats, StatsOptions, compute_stats

MAX_PAGE_COUNT = 1_000_000


def _compute_estimated_pages(
    _emit_line: EmitLine,
    _emit_progress: EmitProgress,
    path: Path,
) -> BookStats:
    """Otwiera EPUB i liczy statystyki z domyślnymi opcjami modułu stats."""
    with Epub(path) as epub:
        return compute_stats(epub, StatsOptions())


class MetadataPages(QWidget):
    """Edytor opcjonalnej liczby stron wraz z asynchroniczną estymacją."""

    status_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path: Path | None = None
        self._supports_pages = False
        self._generation = 0
        self._worker: Worker | None = None
        self._worker_context: tuple[int, Path] | None = None
        self._build_ui()
        self.set_document(None, supported=False, page_count=None)

    def _build_ui(self) -> None:
        """Buduje pole, przycisk i objaśnienia bez lokalnego QSS."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.page_count = QSpinBox()
        self.page_count.setRange(0, MAX_PAGE_COUNT)
        self.page_count.setSpecialValueText("—")
        self.page_count.setAccelerated(True)
        self._field_tooltip = _(
            "Liczba stron zapisywana w EPUB 3 jako schema:numberOfPages. "
            "Wartość „—” oznacza brak i usuwa istniejący wpis przy zapisie."
        )
        self.page_count.setToolTip(self._field_tooltip)
        row.addWidget(self.page_count, stretch=1)

        self.calculate_button = QPushButton(_("Oblicz"))
        self._calculate_tooltip = _(
            "Szacuje liczbę stron z liczby słów przy użyciu modułu Statystyki"
        )
        self.calculate_button.setToolTip(self._calculate_tooltip)
        self.calculate_button.clicked.connect(self._start_calculation)
        row.addWidget(self.calculate_button)
        layout.addLayout(row)

        self.estimate_notice = QLabel(
            _(
                "Wynik „Oblicz” jest estymacją na podstawie liczby słów "
                "(domyślnie 250 słów na stronę), nie liczbą stron wydania papierowego."
            )
        )
        self.estimate_notice.setWordWrap(True)
        layout.addWidget(self.estimate_notice)

        self.epub2_notice = QLabel(
            _("Liczbę stron można zapisać dopiero po konwersji pliku do EPUB 3.")
        )
        self.epub2_notice.setWordWrap(True)
        self.epub2_notice.setEnabled(False)
        layout.addWidget(self.epub2_notice)

    def set_document(
        self,
        path: Path | None,
        *,
        supported: bool,
        page_count: int | None,
    ) -> None:
        """Ustawia książkę i zeruje stan po poprzednim wyborze.

        Args:
            path: ścieżka bieżącego EPUB-a albo ``None``.
            supported: czy OPF bieżącej książki jest w wersji EPUB 3.
            page_count: istniejąca dodatnia liczba stron albo ``None``.
        """
        self._generation += 1
        self._path = path
        self._supports_pages = path is not None and supported
        self.set_page_count(page_count)
        self.epub2_notice.setVisible(path is not None and not supported)
        self._refresh_actions()

    def set_page_count(self, value: int | None) -> bool:
        """Wpisuje poprawną wartość do pola; ``None`` ustawia stan pusty.

        Args:
            value: dodatnia liczba całkowita albo ``None``.

        Returns:
            ``True``, jeśli wartość była pusta lub mieściła się w dozwolonym zakresie.
        """
        if value is None:
            self.page_count.setValue(0)
            return True
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 1 <= value <= MAX_PAGE_COUNT
        ):
            return False
        self.page_count.setValue(value)
        return True

    def value(self) -> int | None:
        """Zwraca dodatnią wartość pola lub ``None`` dla stanu „—”."""
        value = self.page_count.value()
        return value if value > 0 else None

    @property
    def supports_pages(self) -> bool:
        """Czy bieżący dokument może zapisać ``schema:numberOfPages``."""
        return self._supports_pages

    def apply_fetched_value(self, value: int) -> bool:
        """Nanosi liczbę stron z katalogu, o ile bieżący EPUB ją obsługuje."""
        return self._supports_pages and self.set_page_count(value)

    def _refresh_actions(self) -> None:
        """Synchronizuje aktywność pola i przycisku ze stanem książki/workera."""
        available = self._supports_pages and self._path is not None
        self.page_count.setEnabled(available)
        self.calculate_button.setEnabled(available and self._worker is None)
        if self._path is not None and not self._supports_pages:
            tooltip = _(
                "EPUB 2 nie obsługuje schema:numberOfPages; najpierw uaktualnij plik do EPUB 3."
            )
            self.page_count.setToolTip(tooltip)
            self.calculate_button.setToolTip(tooltip)
        else:
            self.page_count.setToolTip(self._field_tooltip)
            self.calculate_button.setToolTip(self._calculate_tooltip)

    def _start_calculation(self) -> None:
        """Uruchamia ``compute_stats`` w istniejącym Workerze."""
        if self._worker is not None or self._path is None or not self._supports_pages:
            return
        path = self._path
        self._worker_context = (self._generation, path)
        worker = Worker(_compute_estimated_pages, path)
        worker.done.connect(self._on_calculated)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_finished)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        self._refresh_actions()
        self.status_changed.emit(_("Obliczanie…"))
        worker.start()

    def _result_is_current(self) -> bool:
        """Czy callback workera nadal dotyczy widocznej książki."""
        return self._worker_context == (self._generation, self._path)

    @Slot(object)
    def _on_calculated(self, result: object) -> None:
        """Nanosi estymację, ale nigdy nie zapisuje EPUB-a automatycznie."""
        if not self._result_is_current():
            return
        if not isinstance(result, BookStats):
            self._show_error(_("Worker statystyk zwrócił niepoprawny wynik."))
            return
        pages = result.estimated_pages
        if not self.set_page_count(pages):
            self._show_error(_("Nie udało się wyznaczyć dodatniej liczby stron."))
            return
        self.status_changed.emit(
            _(
                "Wstawiono szacunkową liczbę stron: {n}. Kliknij Zapisz, aby utrwalić zmianę."
            ).format(n=pages)
        )

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        """Pokazuje błąd obliczeń tylko dla nadal wybranej książki."""
        if self._result_is_current():
            self._show_error(
                _("Nie udało się obliczyć liczby stron: {error}").format(error=message)
            )

    @Slot()
    def _on_finished(self) -> None:
        """Zwalnia zakończony worker i odblokowuje obliczanie."""
        self._worker = None
        self._worker_context = None
        self._refresh_actions()

    def _show_error(self, message: str) -> None:
        """Pokazuje błąd w statusie i w czytelnym dialogu."""
        self.status_changed.emit(message)
        QMessageBox.critical(self, _("Metadane"), message)
