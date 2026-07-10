"""Dialog „Pobierz metadane…" — pobieranie i wybór metadanych po ISBN (Qt).

Warstwa GUI nad :mod:`epubforge.bookmeta`: pobiera rekord w :class:`Worker` (nie
blokuje UI), a następnie pokazuje podgląd z **checkboxami per pole**. Zasada:
nigdy ciche nadpisanie — pola skalarne są domyślnie zaznaczone tylko wtedy, gdy
odpowiadające pole formularza jest puste; deskryptory przedmiotowe BN to osobna
lista, domyślnie **odznaczona**.

Dialog niczego nie zapisuje — zwraca :class:`FetchResult`, a zakładka metadanych
sama nanosi wybór na formularz (i liczbę stron przy zapisie do OPF).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from epubforge.bookmeta import BookRecord, chain
from epubforge.core import Metadata
from epubforge.gui.workers import EmitLine, EmitProgress, Worker
from epubforge.i18n import _

# Pola skalarne oferowane w podglądzie: atrybut BookRecord/Metadata → etykieta.
_SCALAR_FIELDS: tuple[tuple[str, str], ...] = (
    ("title", _("Tytuł")),
    ("publisher", _("Wydawca")),
    ("date", _("Data")),
    ("language", _("Język")),
    ("series", _("Cykl")),
    ("description", _("Opis")),
)


@dataclass
class FetchResult:
    """Wybór użytkownika z dialogu — co nanieść na formularz metadanych.

    Attributes:
        fields: zaznaczone pola skalarne (atrybut → nowa wartość).
        creators: nowa lista autorów, jeśli zaznaczono; ``None`` = bez zmian.
        add_subjects: deskryptory BN do **dopisania** do tematów.
        page_count: liczba stron do zapisania (EPUB 3) lub ``None``.
    """

    fields: dict[str, str] = field(default_factory=dict)
    creators: list[str] | None = None
    add_subjects: list[str] = field(default_factory=list)
    page_count: int | None = None


def _fetch_worker(emit_line: EmitLine, emit_progress: EmitProgress, isbn: str) -> BookRecord | None:
    """Funkcja robocza wątku: odpytuje łańcuch providerów (bez dotykania GUI)."""
    return chain.fetch_by_isbn(isbn)


class FetchMetadataDialog(QDialog):
    """Dialog pobierania metadanych po ISBN z podglądem i wyborem pól."""

    def __init__(
        self,
        current: Metadata,
        *,
        prefill_isbn: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._current = current
        self._record: BookRecord | None = None
        self._worker: Worker | None = None
        self._result = FetchResult()

        # Widgety wyboru budowane po pobraniu rekordu.
        self._scalar_boxes: dict[str, tuple[QCheckBox, str]] = {}
        self._creators_box: QCheckBox | None = None
        self._creators_value: list[str] = []
        self._pages_box: QCheckBox | None = None
        self._pages_value: int | None = None
        self._subject_boxes: list[QCheckBox] = []

        self.setWindowTitle(_("Pobierz metadane"))
        self.setMinimumWidth(460)
        self._build_layout(prefill_isbn)

    # ── Budowa UI ──────────────────────────────────────────────────────────────

    def _build_layout(self, prefill_isbn: str) -> None:
        """Składa układ dialogu: pole ISBN, obszar wyników, przyciski."""
        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("ISBN:"))
        self.isbn_edit = QLineEdit(prefill_isbn)
        self.isbn_edit.setPlaceholderText(_("ISBN książki (10 lub 13 cyfr)"))
        self.isbn_edit.returnPressed.connect(self._start_fetch)
        search_row.addWidget(self.isbn_edit, stretch=1)
        self.search_button = QPushButton(_("Szukaj"))
        self.search_button.clicked.connect(self._start_fetch)
        search_row.addWidget(self.search_button)
        layout.addLayout(search_row)

        self.status_label = QLabel(_("Podaj ISBN i naciśnij „Szukaj"))
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self._results_host = QWidget()
        self._results_layout = QVBoxLayout(self._results_host)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._results_host)
        layout.addWidget(scroll, stretch=1)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)
        self._ok_button().setEnabled(False)
        layout.addWidget(self.button_box)

    def _ok_button(self) -> QPushButton:
        """Zwraca przycisk OK (włączany dopiero po udanym pobraniu)."""
        button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        assert button is not None
        return button

    # ── Pobieranie ───────────────────────────────────────────────────────────────

    def _start_fetch(self) -> None:
        """Uruchamia pobieranie w wątku roboczym (walidacja ISBN po stronie łańcucha)."""
        if self._worker is not None:
            return
        isbn = self.isbn_edit.text().strip()
        if not isbn:
            self.status_label.setText(_("Podaj ISBN"))
            return
        self._clear_results()
        self._ok_button().setEnabled(False)
        self.search_button.setEnabled(False)
        self.status_label.setText(_("Szukam…"))
        worker = Worker(_fetch_worker, isbn)
        worker.done.connect(self._on_fetched)
        worker.failed.connect(self._on_failed)
        self._worker = worker
        worker.start()

    def _on_fetched(self, result: object) -> None:
        """Obsługuje wynik pobrania: buduje podgląd albo komunikat o braku."""
        self._worker = None
        self.search_button.setEnabled(True)
        if not isinstance(result, BookRecord):
            self.status_label.setText(
                _("Nie znaleziono metadanych dla tego ISBN (albo brak połączenia)")
            )
            return
        self._record = result
        self._build_results(result)
        self.status_label.setText(
            _("Znaleziono metadane (źródło: {source}). Zaznacz pola do nadpisania.").format(
                source=result.source or "?"
            )
        )
        self._ok_button().setEnabled(True)

    def _on_failed(self, message: str) -> None:
        """Awaria wątku (nieoczekiwana — łańcuch zwykle zwraca ``None``)."""
        self._worker = None
        self.search_button.setEnabled(True)
        self.status_label.setText(_("Błąd pobierania: {error}").format(error=message))

    # ── Podgląd wyników ──────────────────────────────────────────────────────────

    def _build_results(self, record: BookRecord) -> None:
        """Buduje checkboxy pól skalarnych, autorów, liczby stron i deskryptorów."""
        self._clear_results()
        for attr, label in _SCALAR_FIELDS:
            value = getattr(record, attr)
            if value:
                self._add_scalar_row(attr, label, str(value))
        if record.creators:
            self._add_creators_row(record.creators)
        if record.page_count is not None:
            self._add_pages_row(record.page_count)
        if record.subjects:
            self._add_subjects_rows(record.subjects)
        self._results_layout.addStretch(1)

    def _add_scalar_row(self, attr: str, label: str, value: str) -> None:
        """Dodaje wiersz pola skalarnego (domyślnie zaznaczony, gdy formularz pusty)."""
        checkbox = QCheckBox(f"{label}: {_shorten(value)}")
        checkbox.setToolTip(value)
        checkbox.setChecked(not getattr(self._current, attr, ""))
        self._results_layout.addWidget(checkbox)
        self._scalar_boxes[attr] = (checkbox, value)

    def _add_creators_row(self, creators: list[str]) -> None:
        """Dodaje wiersz autorów (zastąpienie całej listy; domyślnie gdy brak autorów)."""
        checkbox = QCheckBox(f"{_('Autorzy')}: {_shorten('; '.join(creators))}")
        checkbox.setToolTip("; ".join(creators))
        checkbox.setChecked(not self._current.creators)
        self._results_layout.addWidget(checkbox)
        self._creators_box = checkbox
        self._creators_value = list(creators)

    def _add_pages_row(self, count: int) -> None:
        """Dodaje wiersz liczby stron (zapis do OPF; domyślnie zaznaczony)."""
        checkbox = QCheckBox(
            _("Liczba stron: {count} (zapis do OPF, tylko EPUB 3)").format(count=count)
        )
        checkbox.setChecked(True)
        self._results_layout.addWidget(checkbox)
        self._pages_box = checkbox
        self._pages_value = count

    def _add_subjects_rows(self, subjects: list[str]) -> None:
        """Dodaje nagłówek i checkboxy deskryptorów BN (domyślnie ODznaczone)."""
        header = QLabel(_("Deskryptory (dopisz do tematów):"))
        header.setContentsMargins(0, 6, 0, 0)
        self._results_layout.addWidget(header)
        existing = set(self._current.subjects)
        for subject in subjects:
            checkbox = QCheckBox(subject)
            checkbox.setChecked(False)
            checkbox.setEnabled(subject not in existing)
            if subject in existing:
                checkbox.setToolTip(_("Ten temat jest już przypisany"))
            self._results_layout.addWidget(checkbox)
            self._subject_boxes.append(checkbox)

    def _clear_results(self) -> None:
        """Usuwa poprzednie widgety wyników i czyści rejestry checkboxów."""
        self._scalar_boxes.clear()
        self._creators_box = None
        self._creators_value = []
        self._pages_box = None
        self._pages_value = None
        self._subject_boxes.clear()
        while self._results_layout.count():
            item = self._results_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    # ── Zatwierdzenie ────────────────────────────────────────────────────────────

    def _on_accept(self) -> None:
        """Zbiera zaznaczony wybór do :class:`FetchResult` i zamyka dialog."""
        result = FetchResult()
        for attr, (checkbox, value) in self._scalar_boxes.items():
            if checkbox.isChecked():
                result.fields[attr] = value
        if self._creators_box is not None and self._creators_box.isChecked():
            result.creators = list(self._creators_value)
        if self._pages_box is not None and self._pages_box.isChecked():
            result.page_count = self._pages_value
        result.add_subjects = [
            box.text() for box in self._subject_boxes if box.isChecked() and box.isEnabled()
        ]
        self._result = result
        self.accept()

    def result_selection(self) -> FetchResult:
        """Zwraca wybór użytkownika (sensowny po zaakceptowaniu dialogu)."""
        return self._result


def _shorten(text: str, limit: int = 60) -> str:
    """Skraca długą wartość do podglądu w checkboxie (pełna trafia do tooltipa)."""
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[: limit - 1]}…"
