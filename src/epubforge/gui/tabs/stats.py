"""Zakładka „Statystyki" — liczby książki, top-słowa, rozdziały, raport HTML."""

from __future__ import annotations

import tempfile
import webbrowser
from pathlib import Path
from typing import cast

from chodzkos_gui_kit.qt.dialogs import save_file
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from epubforge import __version__
from epubforge.core import Epub
from epubforge.core.config import Config
from epubforge.gui.widgets import PathEntry, Section
from epubforge.gui.workers import EmitLine, EmitProgress, Worker
from epubforge.i18n import _
from epubforge.stats import BookStats, StatsOptions, compute_stats, render_report_html


def _langdetect_available() -> bool:
    """Czy zainstalowano opcjonalny ``langdetect`` (extra ``[stats]``)."""
    try:
        import langdetect  # noqa: F401
    except ImportError:
        return False
    return True


class StatsTab(QWidget):
    """Statystyki książki: karty liczb, top-słowa, rozdziały i raport HTML."""

    def __init__(self, parent: QWidget | None = None, *, config: Config | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._stats: BookStats | None = None
        self._running = False
        self._worker: Worker | None = None
        self._cards: dict[str, QLabel] = {}
        self._build_ui()
        self._refresh_actions()

    # ── Budowa UI ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        row = QHBoxLayout()
        self.path_entry = PathEntry(
            mode="file",
            filetypes=[(_("Pliki EPUB"), "*.epub")],
            placeholder=_("Wskaż plik EPUB…"),
            config=self._config,
            remember_key="stats_last_dir",
        )
        row.addWidget(self.path_entry, stretch=1)
        self.compute_button = QPushButton(_("Oblicz"))
        self.compute_button.clicked.connect(self._compute)
        row.addWidget(self.compute_button)
        outer.addLayout(row)

        if not _langdetect_available():
            notice = QLabel(
                _("Język z metadanych — zainstaluj epubforge[stats] dla wykrywania języka.")
            )
            notice.setWordWrap(True)
            outer.addWidget(notice)

        outer.addWidget(self._build_cards())
        outer.addLayout(self._build_panels(), stretch=1)
        outer.addLayout(self._build_actions())

        self.status_label = QLabel(_("Wskaż plik EPUB i kliknij „Oblicz”."))
        outer.addWidget(self.status_label)

    def _build_cards(self) -> QWidget:
        """Buduje rząd kart liczbowych (słowa / strony / czas / język)."""
        section = Section(_("Podsumowanie"))
        row = QHBoxLayout()
        for key, label in (
            ("words", _("Słowa")),
            ("pages", _("Szac. strony")),
            ("time", _("Czas czytania")),
            ("language", _("Język")),
        ):
            box = QVBoxLayout()
            value = QLabel("—")
            value.setStyleSheet("font-size: 20px; font-weight: bold;")
            caption = QLabel(label)
            box.addWidget(value)
            box.addWidget(caption)
            self._cards[key] = value
            row.addLayout(box)
        row.addStretch(1)
        section.content_layout().addLayout(row)
        return section

    def _build_panels(self) -> QHBoxLayout:
        """Buduje listę top-słów obok tabeli rozdziałów."""
        panels = QHBoxLayout()
        top_section = Section(_("Najczęstsze słowa"))
        self.top_list = QListWidget()
        top_section.add_widget(self.top_list)
        panels.addWidget(top_section, stretch=1)

        chapters_section = Section(_("Rozdziały"))
        self.chapters_tree = QTreeWidget()
        self.chapters_tree.setHeaderLabels([_("Tytuł"), _("Słowa")])
        self.chapters_tree.setRootIsDecorated(False)
        chapters_section.add_widget(self.chapters_tree)
        panels.addWidget(chapters_section, stretch=2)
        return panels

    def _build_actions(self) -> QHBoxLayout:
        """Buduje przyciski eksportu i otwarcia raportu."""
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.export_button = QPushButton(_("Eksport HTML…"))
        self.export_button.clicked.connect(self._export_html)
        actions.addWidget(self.export_button)
        self.open_button = QPushButton(_("Otwórz raport"))
        self.open_button.setToolTip(_("Zapisuje raport tymczasowo i otwiera w przeglądarce"))
        self.open_button.clicked.connect(self._open_report)
        actions.addWidget(self.open_button)
        return actions

    # ── Liczenie ──────────────────────────────────────────────────────────────

    def _compute(self) -> None:
        """Uruchamia liczenie statystyk dla wskazanego pliku w wątku roboczym."""
        path = self.path_entry.get().strip()
        if not path or self._running:
            self._set_status(_("Wskaż plik EPUB"))
            return
        self._running = True
        self._refresh_actions()
        self._set_status(_("Liczenie…"))
        self._worker = Worker(_run_stats_worker, Path(path), StatsOptions())
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, result: object) -> None:
        """Wypełnia karty, top-słowa i rozdziały z policzonych statystyk."""
        self._running = False
        self._stats = cast(BookStats, result)
        self._fill_cards(self._stats)
        self.top_list.clear()
        for word, count in self._stats.top_words:
            self.top_list.addItem(f"{word}  ·  {count}")
        self.chapters_tree.clear()
        for index, chapter in enumerate(self._stats.chapters, start=1):
            title = chapter.title or _("Rozdział {n}").format(n=index)
            self.chapters_tree.addTopLevelItem(QTreeWidgetItem([title, str(chapter.words)]))
        self._set_status(_("Gotowe"))
        self._refresh_actions()

    def _on_failed(self, message: str) -> None:
        """Obsługuje błąd liczenia statystyk."""
        self._running = False
        self._set_status(_("Błąd: {error}").format(error=message))
        self._refresh_actions()

    def _fill_cards(self, stats: BookStats) -> None:
        """Aktualizuje wartości kart liczbowych."""
        language = stats.language or "—"
        if stats.language and stats.language_source != "none":
            language = f"{stats.language} ({stats.language_source})"
        self._cards["words"].setText(str(stats.words))
        self._cards["pages"].setText(str(stats.estimated_pages))
        self._cards["time"].setText(_format_minutes(stats.reading_time_min))
        self._cards["language"].setText(language)

    # ── Raport ──────────────────────────────────────────────────────────────--

    def _export_html(self) -> None:
        """Zapisuje raport HTML do wskazanego pliku."""
        if self._stats is None:
            return
        path = save_file(self, _("Eksport raportu HTML"), "", _("HTML (*.html)"), self._config)
        if not path:
            return
        Path(path).write_text(render_report_html(self._stats, __version__), encoding="utf-8")
        self._set_status(_("Zapisano raport: {name}").format(name=Path(path).name))

    def _open_report(self) -> None:
        """Zapisuje raport do pliku tymczasowego i otwiera w przeglądarce."""
        if self._stats is None:
            return
        tmp = Path(tempfile.gettempdir()) / "epubforge-stats.html"
        tmp.write_text(render_report_html(self._stats, __version__), encoding="utf-8")
        webbrowser.open(tmp.as_uri())
        self._set_status(_("Otwarto raport w przeglądarce"))

    # ── Stan ────────────────────────────────────────────────────────────────--

    def _refresh_actions(self) -> None:
        """Włącza eksport/otwarcie raportu tylko gdy są policzone statystyki."""
        has_stats = self._stats is not None and not self._running
        self.export_button.setEnabled(has_stats)
        self.open_button.setEnabled(has_stats)
        self.compute_button.setEnabled(not self._running)

    def _set_status(self, text: str) -> None:
        """Ustawia tekst paska statusu zakładki."""
        self.status_label.setText(text)


def _run_stats_worker(
    _emit_line: EmitLine,
    _emit_progress: EmitProgress,
    path: Path,
    options: StatsOptions,
) -> BookStats:
    """Otwiera EPUB i liczy statystyki w wątku roboczym."""
    with Epub(path) as epub:
        return compute_stats(epub, options)


def _format_minutes(minutes: int) -> str:
    """Formatuje minuty jako ``h:mm`` albo ``N min``."""
    if minutes >= 60:
        return f"{minutes // 60}:{minutes % 60:02d} h"
    return f"{minutes} min"
