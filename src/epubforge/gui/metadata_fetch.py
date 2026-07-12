"""Dialog „Pobierz metadane…" — pobieranie i wybór metadanych (Qt).

Warstwa GUI nad :mod:`epubforge.bookmeta`: pobiera rekord w :class:`Worker` (nie
blokuje UI), a następnie pokazuje podgląd z **checkboxami per pole**. Zasada:
nigdy ciche nadpisanie — pola skalarne są domyślnie zaznaczone tylko wtedy, gdy
odpowiadające pole formularza jest puste; deskryptory przedmiotowe BN to osobna
lista, domyślnie **odznaczona**.

Dwie ścieżki: po **ISBN** (łańcuch BN → LC → OL → GB) oraz — dla plików bez ISBN —
po **tytule/autorze** (LubimyCzytac): wyszukiwarka zwraca listę kandydatów z oceną
dopasowania; użytkownik wybiera, a dopiero wtedy pobierany jest pełny rekord. Poniżej
progu pewności nic nie jest wybierane automatycznie.

Dialog niczego nie zapisuje — zwraca :class:`FetchResult`, a zakładka metadanych
sama nanosi wybór na formularz (i liczbę stron przy zapisie do OPF).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from epubforge.bookmeta import BookRecord, Candidate, chain
from epubforge.core import Metadata
from epubforge.gui.workers import EmitLine, EmitProgress, Worker
from epubforge.i18n import _

# Rola danych elementu listy przechowująca obiekt Candidate.
_CANDIDATE_ROLE = int(Qt.ItemDataRole.UserRole)

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


def _fetch_worker(
    emit_line: EmitLine,
    emit_progress: EmitProgress,
    isbn: str,
    title: str,
    author: str,
) -> BookRecord | None:
    """Funkcja robocza wątku: odpytuje łańcuch providerów po ISBN (bez dotykania GUI).

    ``title``/``author`` (z metadanych EPUB) idą jako podpowiedź — BN użyje ich do
    fallbacku po tytule, gdy ISBN e-wydania nie ma w katalogu.
    """
    return chain.fetch_by_isbn(isbn, title=title, author=author)


def _search_worker(
    emit_line: EmitLine, emit_progress: EmitProgress, title: str, author: str
) -> list[Candidate]:
    """Funkcja robocza wątku: wyszukuje kandydatów po tytule/autorze (LC)."""
    return chain.search_candidates(title, author)


def _candidate_worker(
    emit_line: EmitLine, emit_progress: EmitProgress, candidate: Candidate
) -> BookRecord | None:
    """Funkcja robocza wątku: pobiera pełny rekord wybranego kandydata."""
    return chain.fetch_candidate(candidate)


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
        self.setMinimumWidth(480)
        self._build_layout(prefill_isbn)

    # ── Budowa UI ──────────────────────────────────────────────────────────────

    def _build_layout(self, prefill_isbn: str) -> None:
        """Składa układ dialogu: wyszukiwanie (ISBN / tytuł+autor), wyniki, przyciski."""
        layout = QVBoxLayout(self)

        isbn_row = QHBoxLayout()
        isbn_row.addWidget(QLabel("ISBN:"))
        self.isbn_edit = QLineEdit(prefill_isbn)
        self.isbn_edit.setPlaceholderText(_("ISBN książki (10 lub 13 cyfr)"))
        self.isbn_edit.returnPressed.connect(self._start_fetch)
        isbn_row.addWidget(self.isbn_edit, stretch=1)
        self.search_button = QPushButton(_("Szukaj"))
        self.search_button.clicked.connect(self._start_fetch)
        isbn_row.addWidget(self.search_button)
        layout.addLayout(isbn_row)

        layout.addLayout(self._build_title_author_row())

        self.status_label = QLabel(_("Podaj ISBN i naciśnij „Szukaj"))
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Lista kandydatów (tryb bez ISBN) — ukryta, dopóki nie ma wyników.
        self.candidates_list = QListWidget()
        self.candidates_list.setToolTip(_("Dwuklik pobiera pełne metadane wybranej książki"))
        self.candidates_list.itemDoubleClicked.connect(self._on_candidate_activated)
        self.candidates_list.setMaximumHeight(150)
        self.candidates_list.hide()
        layout.addWidget(self.candidates_list)

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

    def _build_title_author_row(self) -> QHBoxLayout:
        """Buduje wiersz wyszukiwania po tytule i autorze (dla plików bez ISBN)."""
        row = QHBoxLayout()
        self.title_edit = QLineEdit(self._current.title)
        self.title_edit.setPlaceholderText(_("Tytuł"))
        row.addWidget(self.title_edit, stretch=2)
        author = self._current.creators[0] if self._current.creators else ""
        self.author_edit = QLineEdit(author)
        self.author_edit.setPlaceholderText(_("Autor"))
        row.addWidget(self.author_edit, stretch=2)
        self.title_search_button = QPushButton(_("Szukaj wg tytułu"))
        self.title_search_button.setToolTip(
            _("Wyszukuje kandydatów w LubimyCzytac (gdy nie masz ISBN)")
        )
        self.title_search_button.clicked.connect(self._start_candidate_search)
        row.addWidget(self.title_search_button)
        return row

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
        self.candidates_list.hide()
        self._ok_button().setEnabled(False)
        self._set_busy(True)
        self.status_label.setText(_("Szukam…"))
        # Tytuł/autor z pól dialogu (prefill z metadanych EPUB) → podpowiedź dla fallbacku BN.
        title = self.title_edit.text().strip()
        author = self.author_edit.text().strip()
        worker = Worker(_fetch_worker, isbn, title, author)
        worker.done.connect(self._on_fetched)
        worker.failed.connect(self._on_failed)
        self._worker = worker
        worker.start()

    def _on_fetched(self, result: object) -> None:
        """Obsługuje wynik pobrania: buduje podgląd albo komunikat o braku."""
        self._worker = None
        self._set_busy(False)
        if not isinstance(result, BookRecord):
            self.status_label.setText(
                _("Nie znaleziono metadanych dla tego ISBN (albo brak połączenia)")
            )
            return
        self._record = result
        self._build_results(result)
        if result.match_type == "fuzzy":
            # Dopasowano po tytule (ISBN e-wydania nieobecny w katalogu) — użytkownik ma
            # świadomie zaakceptować; ISBN pliku NIE jest nadpisywany.
            self.status_label.setText(
                _(
                    "Znaleziono (dopasowanie po tytule — ISBN e-wydania nieobecny w BN, "
                    "źródło: {source}). Zweryfikuj i zaznacz pola do nadpisania."
                ).format(source=result.source or "?")
            )
        else:
            self.status_label.setText(
                _("Znaleziono metadane (źródło: {source}). Zaznacz pola do nadpisania.").format(
                    source=result.source or "?"
                )
            )
        self._ok_button().setEnabled(True)

    def _on_failed(self, message: str) -> None:
        """Awaria wątku (nieoczekiwana — łańcuch zwykle zwraca ``None``)."""
        self._worker = None
        self._set_busy(False)
        self.status_label.setText(_("Błąd pobierania: {error}").format(error=message))

    def _set_busy(self, busy: bool) -> None:
        """Blokuje/odblokowuje przyciski wyszukiwania na czas pracy wątku."""
        self.search_button.setEnabled(not busy)
        self.title_search_button.setEnabled(not busy)

    # ── Wyszukiwanie po tytule/autorze (tryb bez ISBN) ───────────────────────────

    def _start_candidate_search(self) -> None:
        """Uruchamia wyszukiwanie kandydatów w LC po tytule i autorze."""
        if self._worker is not None:
            return
        title = self.title_edit.text().strip()
        if not title:
            self.status_label.setText(_("Podaj tytuł do wyszukania"))
            return
        author = self.author_edit.text().strip()
        self._clear_results()
        self.candidates_list.clear()
        self.candidates_list.hide()
        self._ok_button().setEnabled(False)
        self._set_busy(True)
        self.status_label.setText(_("Szukam…"))
        worker = Worker(_search_worker, title, author)
        worker.done.connect(self._on_candidates)
        worker.failed.connect(self._on_failed)
        self._worker = worker
        worker.start()

    def _on_candidates(self, result: object) -> None:
        """Wypełnia listę kandydatów wynikami wyszukiwania (bez auto-wyboru)."""
        self._worker = None
        self._set_busy(False)
        candidates = result if isinstance(result, list) else []
        if not candidates:
            self.status_label.setText(_("Nie znaleziono książek dla tego tytułu/autora"))
            return
        self.candidates_list.clear()
        for candidate in candidates:
            item = QListWidgetItem(_candidate_label(candidate))
            item.setData(_CANDIDATE_ROLE, candidate)
            self.candidates_list.addItem(item)
        self.candidates_list.show()
        self.status_label.setText(
            _("Znaleziono {n} kandydatów — dwuklik wybiera i pobiera pełne dane").format(
                n=len(candidates)
            )
        )

    def _on_candidate_activated(self, item: QListWidgetItem) -> None:
        """Pobiera pełny rekord dla dwuklikniętego kandydata."""
        if self._worker is not None:
            return
        candidate = item.data(_CANDIDATE_ROLE)
        if not isinstance(candidate, Candidate):
            return
        self._clear_results()
        self._ok_button().setEnabled(False)
        self._set_busy(True)
        self.status_label.setText(_("Pobieram metadane wybranej książki…"))
        worker = Worker(_candidate_worker, candidate)
        worker.done.connect(self._on_fetched)
        worker.failed.connect(self._on_failed)
        self._worker = worker
        worker.start()

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
            if item is None:
                continue
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


def _candidate_label(candidate: Candidate) -> str:
    """Buduje etykietę kandydata na listę: tytuł — autorzy (rok) [dopasowanie]."""
    authors = ", ".join(candidate.authors)
    parts = [candidate.title]
    if authors:
        parts.append(f"— {authors}")
    if candidate.year:
        parts.append(f"({candidate.year})")
    parts.append(f"· {round(candidate.score * 100)}%")
    return " ".join(parts)
