"""Panel Szukaj/Zamień dla zakładki Edytor (Qt).

Logika wyszukiwania/zamiany jest czysta (``epubforge.core.search``); ten widget
tylko ją ubiera w UI i spina z edytorem przez protokół :class:`SearchHost`.
Wyszukiwanie i zamiana biegną w :class:`Worker` (duże książki, anulowanie,
regex poza wątkiem GUI).
"""

from __future__ import annotations

from typing import Protocol, cast, runtime_checkable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from epubforge.core import Epub
from epubforge.core.search import (
    REGEX_TIMEOUT_MESSAGE,
    ReplaceReport,
    SearchHit,
    SearchResults,
    replace_in_epub,
    search_epub,
)
from epubforge.gui.workers import EmitLine, EmitProgress, ShouldCancel, Worker
from epubforge.i18n import _, ngettext

# Rola przechowująca lokalizację trafienia w wierszu drzewa: (path, line, column).
_HIT_ROLE = Qt.ItemDataRole.UserRole


@runtime_checkable
class SearchHost(Protocol):
    """Kontrakt zakładki Edytor wykorzystywany przez panel Szukaj/Zamień."""

    def search_epub_instance(self) -> Epub | None:
        """Zwraca otwarty EPUB albo ``None``."""

    def current_internal_path(self) -> str | None:
        """Zwraca ścieżkę aktualnie wyświetlanego pliku albo ``None``."""

    def flush_current_editor(self) -> None:
        """Zapisuje niezapisane zmiany bieżącego pliku do bufora EPUB (sync _dirty)."""

    def jump_to_hit(self, internal_path: str, line: int, column: int) -> None:
        """Otwiera plik w edytorze i ustawia kursor na trafieniu."""

    def mark_replaced(self, paths: list[str]) -> None:
        """Oznacza pliki jako zmienione (bufor) i odświeża widok/drzewo."""

    def set_mutation_guard(self, active: bool) -> None:
        """Włącza/wyłącza guard mutacji dokumentu (edytor + lifecycle)."""


class SearchReplacePanel(QWidget):
    """Panel Szukaj/Zamień przeszukujący pliki tekstowe EPUB-a."""

    RESULT_PAGE_SIZE = 500

    def __init__(self, host: SearchHost, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._worker: Worker | None = None
        self._workers: set[Worker] = set()
        self._searching = False
        self._cancellable = False
        self._search_generation = 0
        self._result_hits: list[SearchHit] = []
        self._result_groups: dict[str, QTreeWidgetItem] = {}
        self._result_totals: dict[str, int] = {}
        self._rendered_results = 0
        self._result_truncated = False
        self._build_ui()
        self.setVisible(False)

    # ── Budowa UI ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        fields = QHBoxLayout()
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText(_("Szukaj…"))
        self.search_field.setToolTip(_("Fraza lub wyrażenie regularne do wyszukania"))
        self.search_field.textChanged.connect(self._on_query_changed)
        self.search_field.returnPressed.connect(self._on_search)
        fields.addWidget(self.search_field, stretch=1)
        self.replace_field = QLineEdit()
        self.replace_field.setPlaceholderText(_("Zamień na…"))
        self.replace_field.setToolTip(_("Tekst podstawiany przez operację Zamień wszystkie"))
        fields.addWidget(self.replace_field, stretch=1)
        layout.addLayout(fields)

        options = QHBoxLayout()
        self.regex_check = QCheckBox(_("Regex"))
        self.regex_check.setToolTip(_("Traktuj frazę jako wyrażenie regularne"))
        options.addWidget(self.regex_check)
        self.case_check = QCheckBox(_("Aa"))
        self.case_check.setToolTip(_("Rozróżniaj wielkość liter"))
        options.addWidget(self.case_check)
        self.words_check = QCheckBox(_("Całe słowa"))
        self.words_check.setToolTip(_("Dopasuj tylko całe słowa"))
        options.addWidget(self.words_check)

        self.scope_group = QButtonGroup(self)
        self.scope_current = QRadioButton(_("Bieżący plik"))
        self.scope_all = QRadioButton(_("Cały EPUB"))
        self.scope_current.setToolTip(_("Ogranicz wyszukiwanie do aktualnie otwartego pliku"))
        self.scope_all.setToolTip(_("Przeszukaj wszystkie tekstowe pliki publikacji"))
        self.scope_all.setChecked(True)
        self.scope_group.addButton(self.scope_current)
        self.scope_group.addButton(self.scope_all)
        options.addSpacing(12)
        options.addWidget(self.scope_current)
        options.addWidget(self.scope_all)
        options.addStretch(1)
        layout.addLayout(options)

        actions = QHBoxLayout()
        self.search_button = QPushButton(_("Szukaj"))
        self.search_button.setToolTip(_("Uruchom wyszukiwanie z wybranymi opcjami"))
        self.search_button.clicked.connect(self._on_search)
        actions.addWidget(self.search_button)
        self.replace_button = QPushButton(_("Zamień wszystkie"))
        self.replace_button.setToolTip(
            _("Zastąp wszystkie trafienia w wybranym zakresie i pokaż podsumowanie")
        )
        self.replace_button.clicked.connect(self._on_replace_all)
        actions.addWidget(self.replace_button)
        self.cancel_button = QPushButton(_("Anuluj"))
        self.cancel_button.setToolTip(_("Anuluj wyszukiwanie"))
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._on_cancel)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        self.close_button = QPushButton(_("Zamknij"))
        self.close_button.setToolTip(_("Ukryj panel Szukaj/Zamień"))
        self.close_button.clicked.connect(lambda: self.setVisible(False))
        actions.addWidget(self.close_button)
        layout.addLayout(actions)

        self.results = QTreeWidget()
        self.results.setHeaderHidden(True)
        self.results.itemDoubleClicked.connect(self._on_result_double_clicked)
        layout.addWidget(self.results, stretch=1)

        self.show_more_button = QPushButton(_("Pokaż więcej"))
        self.show_more_button.setToolTip(_("Pokaż kolejną stronę wyników z pamięci"))
        self.show_more_button.setEnabled(False)
        self.show_more_button.clicked.connect(self._show_more_results)
        layout.addWidget(self.show_more_button)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    # ── Sterowanie widocznością ─────────────────────────────────────────────--

    def toggle(self) -> None:
        """Pokazuje/ukrywa panel; przy pokazaniu przenosi fokus na pole szukania.

        Bazuje na :meth:`isHidden` (jawny stan), a nie ``isVisible`` — to drugie
        zależy od widoczności rodzica i myli się dla niepokazanego okna (testy).
        """
        show = self.isHidden()
        self.setVisible(show)
        if show:
            self.search_field.setFocus()
            self.search_field.selectAll()

    # ── Opcje / zakres ──────────────────────────────────────────────────────--

    def _options(self) -> dict[str, bool]:
        return {
            "regex": self.regex_check.isChecked(),
            "case_sensitive": self.case_check.isChecked(),
            "whole_words": self.words_check.isChecked(),
        }

    def _scope_paths(self) -> list[str] | None:
        """Ścieżki dla zakresu: bieżący plik → [ścieżka]; cały EPUB → ``None``."""
        if not self.scope_current.isChecked():
            return None
        current = self._host.current_internal_path()
        return [current] if current else []

    # ── Wyszukiwanie ────────────────────────────────────────────────────────--

    def _on_query_changed(self, _text: str) -> None:
        """Unieważnia stare trafienia i zatrzymuje search rozpoczęty dla innego query."""
        self._search_generation += 1
        self._reset_results()
        self._set_status("")
        if self._worker is not None and self._searching and self._cancellable:
            self._worker.cancel()

    def _on_search(self) -> None:
        if self._searching:
            return
        epub = self._host.search_epub_instance()
        query = self.search_field.text()
        if epub is None:
            self._set_status(_("Otwórz najpierw plik EPUB."))
            return
        if not query:
            self._set_status(_("Podaj frazę do wyszukania."))
            return

        paths = self._scope_paths()
        self._start_search_worker(epub, query, paths)

    def _start_search_worker(self, epub: Epub, query: str, paths: list[str] | None) -> None:
        """Szuka w wątku roboczym (bieżący plik albo cały EPUB, z anulowaniem)."""
        options = self._options()
        self._reset_results()
        self._search_generation += 1
        generation = self._search_generation
        self._searching = True
        self._set_running(True, cancellable=True)
        self._set_status(_("Szukam…"))
        worker = Worker(
            _search_worker,
            epub,
            query,
            options["regex"],
            options["case_sensitive"],
            options["whole_words"],
            paths,
        )
        self._worker = worker
        self._track_worker(worker)
        worker.done.connect(lambda result: self._on_search_done(result, generation))
        worker.failed.connect(lambda message: self._on_search_failed(message, generation))
        worker.cancelled.connect(lambda: self._on_search_cancelled(generation))
        worker.start()

    def _on_search_done(self, result: object, generation: int) -> None:
        if generation != self._search_generation:
            self._finish_stale_search()
            return
        self._searching = False
        self._set_running(False)
        self._populate_results(cast(SearchResults, result))

    def _on_search_failed(self, message: str, generation: int) -> None:
        if generation != self._search_generation:
            self._finish_stale_search()
            return
        self._searching = False
        self._set_running(False)
        self._set_status(message)

    def _on_search_cancelled(self, generation: int) -> None:
        if generation != self._search_generation:
            self._finish_stale_search()
            return
        self._searching = False
        self._set_running(False)
        self._set_status(_("Anulowano"))

    def _finish_stale_search(self) -> None:
        """Zwalnia lifecycle po callbacku search unieważnionego zmianą zapytania."""
        if self._searching and self._cancellable:
            self._searching = False
            self._set_running(False)

    def _on_cancel(self) -> None:
        if self._worker is not None and self._searching and self._cancellable:
            self.cancel_button.setEnabled(False)
            self._worker.cancel()

    # ── Wyniki ──────────────────────────────────────────────────────────────--

    def _populate_results(self, hits: SearchResults) -> None:
        """Buforuje bounded wynik core i materializuje tylko pierwszą stronę Qt."""
        self._reset_results()
        grouped: dict[str, list[SearchHit]] = {}
        for hit in hits:
            grouped.setdefault(hit.internal_path, []).append(hit)
        self._result_totals = {path: len(file_hits) for path, file_hits in grouped.items()}
        self._result_hits = [hit for path in sorted(grouped) for hit in grouped[path]]
        self._result_truncated = hits.truncated
        self._show_more_results()

    def _show_more_results(self) -> None:
        """Dokłada jedną stronę z istniejącego bufora; nie uruchamia ponownie search."""
        end = min(self._rendered_results + self.RESULT_PAGE_SIZE, len(self._result_hits))
        self.results.setUpdatesEnabled(False)
        try:
            for hit in self._result_hits[self._rendered_results : end]:
                group = self._result_groups.get(hit.internal_path)
                if group is None:
                    total = self._result_totals[hit.internal_path]
                    group = QTreeWidgetItem([f"{hit.internal_path} ({total})"])
                    group.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    self.results.addTopLevelItem(group)
                    self._result_groups[hit.internal_path] = group
                    group.setExpanded(True)
                child = QTreeWidgetItem([f"{hit.line}: {hit.preview}"])
                child.setData(0, _HIT_ROLE, (hit.internal_path, hit.line, hit.column))
                group.addChild(child)
        finally:
            self.results.setUpdatesEnabled(True)
        self._rendered_results = end
        self.show_more_button.setEnabled(end < len(self._result_hits))
        self._update_result_status()

    def _reset_results(self) -> None:
        """Czyści bounded bufor i wszystkie zmaterializowane strony GUI."""
        self.results.clear()
        self._result_hits = []
        self._result_groups = {}
        self._result_totals = {}
        self._rendered_results = 0
        self._result_truncated = False
        self.show_more_button.setEnabled(False)

    def _update_result_status(self) -> None:
        """Pokazuje pełną liczność bufora i jawny sygnał truncation core."""
        count = len(self._result_hits)
        if self._result_truncated:
            message = _(
                "Znaleziono co najmniej {n} trafień. Wyniki wyszukiwania ograniczono."
            ).format(n=count)
        else:
            message = ngettext("Znaleziono {n} trafienie", "Znaleziono {n} trafień", count).format(
                n=count
            )
        if self._rendered_results < count:
            message += _(" · pokazano {shown}").format(shown=self._rendered_results)
        self._set_status(message)

    def reset(self) -> None:
        """Anuluje bieżący search i unieważnia wyniki przy zmianie EPUB-a."""
        self._search_generation += 1
        if self._worker is not None and self._searching and self._cancellable:
            self._worker.cancel()
        self._worker = None
        self._searching = False
        self._set_running(False)
        self._reset_results()
        self._set_status("")

    def is_search_running(self) -> bool:
        """Czy worker tylko-odczytowego wyszukiwania nadal używa otwartego EPUB-a."""
        return self._searching and self._cancellable

    def _track_worker(self, worker: Worker) -> None:
        """Trzyma anulowany QThread przy życiu do sygnału finished."""
        self._workers.add(worker)
        worker.finished.connect(lambda: self._release_worker(worker))

    def _release_worker(self, worker: Worker) -> None:
        self._workers.discard(worker)
        if self._worker is worker:
            self._worker = None

    def _on_result_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        location = item.data(0, _HIT_ROLE)
        if isinstance(location, tuple):
            internal_path, line, column = location
            self._host.jump_to_hit(internal_path, line, column)

    # ── Zamiana ─────────────────────────────────────────────────────────────--

    def _on_replace_all(self) -> None:
        if self._searching:
            return
        epub = self._host.search_epub_instance()
        query = self.search_field.text()
        if epub is None or not query:
            self._set_status(_("Otwórz EPUB i podaj frazę."))
            return

        # Nie zgub niezapisanych zmian bieżącego pliku — najpierw sync do bufora.
        self._host.flush_current_editor()
        options = self._options()
        self._searching = True
        self._host.set_mutation_guard(True)
        self._set_running(True, cancellable=False)
        self._set_status(_("Zamieniam…"))
        worker = Worker(
            _replace_worker,
            epub,
            query,
            self.replace_field.text(),
            options["regex"],
            options["case_sensitive"],
            options["whole_words"],
            self._scope_paths(),
        )
        self._worker = worker
        self._track_worker(worker)
        worker.done.connect(self._on_replace_done)
        worker.failed.connect(self._on_replace_failed)
        worker.cancelled.connect(self._on_replace_interrupted)
        worker.start()

    def _on_replace_done(self, result: object) -> None:
        self._finish_replace()
        report = cast(ReplaceReport, result)
        self._host.mark_replaced(report.changed_files)
        self._report_replace(report.total, len(report.changed_files), report.skipped)
        timed_out = any(reason == REGEX_TIMEOUT_MESSAGE for _path, reason in report.skipped)
        if timed_out:
            # Ten sam wzorzec przy search znów trafiłby na timeout i nadpisał status.
            return
        self._on_search()

    def _on_replace_failed(self, message: str) -> None:
        self._finish_replace()
        self._sync_pending_replacements()
        self._set_status(message)

    def _on_replace_interrupted(self) -> None:
        """Fail-safe: stray cancel() nie może zgubić bufora ani zostawić guardu."""
        self._finish_replace()
        self._sync_pending_replacements()
        self._set_status(_("Zamieniono — dokończono zapis do bufora."))

    def _finish_replace(self) -> None:
        self._searching = False
        self._set_running(False)
        self._host.set_mutation_guard(False)

    def _sync_pending_replacements(self) -> None:
        """Oznacza dirty na podstawie bufora EPUB (także po failed/interrupted)."""
        epub = self._host.search_epub_instance()
        if epub is None:
            return
        self._host.mark_replaced(list(epub.pending_changes().modified))

    def _report_replace(self, total: int, files: int, skipped: list[tuple[str, str]]) -> None:
        message = _("Zamieniono {total} w {files} plikach").format(total=total, files=files)
        if skipped:
            message += _(" · pominięto {n}").format(n=len(skipped))
        self._set_status(message)

    # ── Pomocnicze ──────────────────────────────────────────────────────────--

    def _set_running(self, running: bool, *, cancellable: bool = False) -> None:
        self._cancellable = running and cancellable
        self.search_button.setEnabled(not running)
        self.replace_button.setEnabled(not running)
        self.cancel_button.setEnabled(running and cancellable)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)


def _search_worker(
    _emit_line: EmitLine,
    _emit_progress: EmitProgress,
    should_cancel: ShouldCancel,
    epub: Epub,
    query: str,
    regex: bool,
    case_sensitive: bool,
    whole_words: bool,
    paths: list[str] | None,
) -> SearchResults:
    """Funkcja robocza: przeszukuje wskazany zakres (z anulowaniem między plikami)."""
    return search_epub(
        epub,
        query,
        regex=regex,
        case_sensitive=case_sensitive,
        whole_words=whole_words,
        paths=paths,
        should_cancel=should_cancel,
    )


def _replace_worker(
    _emit_line: EmitLine,
    _emit_progress: EmitProgress,
    epub: Epub,
    query: str,
    replacement: str,
    regex: bool,
    case_sensitive: bool,
    whole_words: bool,
    paths: list[str] | None,
) -> ReplaceReport:
    """Funkcja robocza: zamienia w wskazanym zakresie (bez anulowania)."""
    return replace_in_epub(
        epub,
        query,
        replacement,
        regex=regex,
        case_sensitive=case_sensitive,
        whole_words=whole_words,
        paths=paths,
    )
