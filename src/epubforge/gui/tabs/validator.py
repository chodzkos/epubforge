"""Zakładka „Walidacja" — EpubCheck z klikalnymi błędami skaczącymi do edytora.

Wynik walidacji renderujemy w :class:`QTreeWidget`; dwuklik wiersza z lokalizacją
woła ``MainWindow.open_in_editor`` (kontrakt F-C). Gdy brak Javy/epubcheck.jar,
zamiast wyników pokazujemy panel pomocy z instrukcją i wyborem jara.
"""

from __future__ import annotations

import dataclasses
import json
from collections import Counter
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, cast

from chodzkos_gui_kit.palette import Palette as Theme
from chodzkos_gui_kit.qt.dialogs import open_file, save_file
from chodzkos_gui_kit.qt.theme import current_palette as current_theme
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from epubforge.core import ConfigStore, Tool, detect_with_cache
from epubforge.gui.widgets import (
    FileList,
    Section,
    file_list_count_label,
    file_list_texts,
    make_scrollable,
)
from epubforge.gui.workers import EmitLine, EmitProgress, ShouldCancel, Worker
from epubforge.i18n import _, ngettext
from epubforge.validators import (
    AceMessage,
    AceReport,
    Severity,
    ValidationMessage,
    ValidationReport,
    run_ace,
    run_epubcheck,
)

if TYPE_CHECKING:
    from epubforge.gui.app import MainWindow

# Strony QStackedWidget: wyniki / panel pomocy (brak narzędzi).
_PAGE_RESULTS, _PAGE_HELP = 0, 1
# Lokalizacja w wierszu drzewa: krotka ``(internal_path, line)`` pod jedną rolą.
_LOCATION_ROLE = Qt.ItemDataRole.UserRole


@dataclasses.dataclass(frozen=True)
class _ResultRow:
    """Znormalizowany wiersz wyniku wspólny dla EpubChecka i Ace.

    Drzewo pokazuje wyniki obu audytów w tej samej tabeli, więc oba raporty
    sprowadzamy do tego samego kształtu: ``code`` to kod EpubChecka albo reguła
    Ace, a lokalizacja (``internal_path`` + opcjonalna ``line``) napędza skok do
    edytora.
    """

    severity: Severity
    code: str
    internal_path: str | None
    line: int | None
    message: str


def _row_from_message(message: ValidationMessage) -> _ResultRow:
    """Sprowadza komunikat EpubChecka do znormalizowanego wiersza."""
    return _ResultRow(
        severity=message.severity,
        code=message.code,
        internal_path=message.internal_path,
        line=message.line,
        message=message.message,
    )


def _row_from_ace(message: AceMessage) -> _ResultRow:
    """Sprowadza naruszenie Ace do znormalizowanego wiersza (Ace nie podaje linii)."""
    return _ResultRow(
        severity=message.severity,
        code=message.rule,
        internal_path=message.internal_path,
        line=None,
        message=message.message,
    )


class ValidatorTab(QWidget):
    """Walidacja plików EPUB przez EpubCheck z klikalnym raportem."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tools: dict[str, Tool] | None = None,
        config: ConfigStore | None = None,
        main_window: MainWindow | None = None,
    ) -> None:
        super().__init__(parent)
        self.tools = tools if tools is not None else {}
        self._config = config
        self._main_window = main_window
        self._theme: Theme = current_theme()
        self._report: ValidationReport | None = None
        self._ace_report: AceReport | None = None
        self._rows: list[_ResultRow] = []
        self._active_epub: Path | None = None
        self._running = False
        self._worker: Worker | None = None

        self._build_ui()
        self._refresh_tools_state()

    # ── Budowa UI ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(12, 12, 12, 12)

        section = Section(_("Pliki EPUB"))
        self.file_list = FileList(
            extensions={".epub"},
            config=self._config,
            texts=file_list_texts(),
            count_label=file_list_count_label,
        )
        self.file_list.selection_changed.connect(lambda _path: self._refresh_actions())
        self.file_list.files_changed.connect(lambda _files: self._refresh_actions())
        section.add_widget(self.file_list)
        outer.addWidget(section)

        outer.addLayout(self._build_toolbar())

        self.summary_label = QLabel("")
        outer.addWidget(self.summary_label)
        outer.addLayout(self._build_filters())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_tree())
        self.stack.addWidget(self._build_help())
        outer.addWidget(self.stack, stretch=1)

        self.status_label = QLabel(_("Dodaj pliki EPUB i kliknij „Sprawdź zaznaczony”."))
        outer.addWidget(self.status_label)
        outer.addStretch(1)

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(make_scrollable(content))
        self.setLayout(root)

    def _build_toolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        self.check_button = QPushButton(_("Sprawdź zaznaczony"))
        self.check_button.setToolTip(_("Uruchom EpubCheck na zaznaczonym pliku"))
        self.check_button.clicked.connect(self._run_check)
        toolbar.addWidget(self.check_button)
        self.ace_button = QPushButton(_("Sprawdź dostępność (Ace)"))
        self.ace_button.clicked.connect(self._run_ace_check)
        toolbar.addWidget(self.ace_button)
        self.cancel_button = QPushButton(_("Anuluj"))
        self.cancel_button.setToolTip(_("Przerywa trwającą walidację (kończy proces Javy)"))
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        toolbar.addWidget(self.cancel_button)
        # Pasek postępu: EpubCheck nie raportuje procentów, więc w trakcie pracy
        # pokazujemy tryb nieokreślony (range 0,0 = „busy").
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        toolbar.addWidget(self.progress_bar, stretch=1)
        self.export_button = QPushButton(_("Eksport…"))
        self.export_button.setToolTip(_("Zapisz raport jako JSON lub HTML"))
        self.export_button.clicked.connect(self._export_report)
        self.export_button.setEnabled(False)
        toolbar.addWidget(self.export_button)
        return toolbar

    def _build_filters(self) -> QHBoxLayout:
        filters = QHBoxLayout()
        filters.addWidget(QLabel(_("Pokaż:")))
        self.show_errors = self._filter_check(_("Błędy"))
        self.show_warnings = self._filter_check(_("Ostrzeżenia"))
        self.show_info = self._filter_check(_("Informacje"))
        filters.addWidget(self.show_errors)
        filters.addWidget(self.show_warnings)
        filters.addWidget(self.show_info)
        filters.addStretch(1)
        return filters

    def _filter_check(self, label: str) -> QCheckBox:
        """Tworzy checkbox filtra severity (domyślnie zaznaczony)."""
        check = QCheckBox(label)
        check.setChecked(True)
        check.toggled.connect(lambda _checked: self._populate_tree())
        return check

    def _build_tree(self) -> QTreeWidget:
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([_("Poziom"), _("Kod"), _("Plik:linia"), _("Komunikat")])
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0, 110)
        self.tree.setColumnWidth(1, 90)
        self.tree.setColumnWidth(2, 200)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        return self.tree

    def _build_help(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        self.help_label = QLabel()
        self.help_label.setWordWrap(True)
        self.help_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.help_label.setOpenExternalLinks(True)
        box.addWidget(self.help_label)
        pick = QHBoxLayout()
        self.pick_java_button = QPushButton(_("Wskaż java.exe…"))
        self.pick_java_button.clicked.connect(self._pick_java)
        pick.addWidget(self.pick_java_button)
        self.pick_jar_button = QPushButton(_("Wskaż epubcheck.jar…"))
        self.pick_jar_button.clicked.connect(self._pick_jar)
        pick.addWidget(self.pick_jar_button)
        pick.addStretch(1)
        box.addLayout(pick)
        box.addStretch(1)
        return page

    # ── Stan narzędzi ─────────────────────────────────────────────────────────

    def _tools_ready(self) -> bool:
        """Czy ``java`` (≥11) i ``epubcheck.jar`` są dostępne."""
        java = self.tools.get("java")
        jar = self.tools.get("epubcheck")
        return bool(java and java.available and jar and jar.available)

    def _ace_ready(self) -> bool:
        """Czy narzędzie ``ace`` (DAISY) jest dostępne."""
        ace = self.tools.get("ace")
        return bool(ace and ace.available)

    def _refresh_tools_state(self) -> None:
        """Pokazuje wyniki albo panel pomocy zależnie od dostępności narzędzi.

        Panel wyników pokazujemy, gdy dostępny jest KTÓRYKOLWIEK audyt (EpubCheck
        lub Ace); panel pomocy (o instalacji Javy/epubchecka) tylko gdy nie ma
        żadnego.
        """
        ready = self._tools_ready() or self._ace_ready()
        self.stack.setCurrentIndex(_PAGE_RESULTS if ready else _PAGE_HELP)
        if not ready:
            self.help_label.setText(self._help_html())
        self._refresh_actions()

    def _refresh_actions(self) -> None:
        """Aktualizuje stan przycisków (zależnie od narzędzi, pliku, trwającej pracy)."""
        has_file = self.file_list.current_path() is not None
        self.check_button.setEnabled(self._tools_ready() and has_file and not self._running)
        self.ace_button.setEnabled(self._ace_ready() and has_file and not self._running)
        self.ace_button.setToolTip(
            _("Uruchom audyt dostępności DAISY Ace na zaznaczonym pliku")
            if self._ace_ready()
            else _("Zainstaluj DAISY Ace (Node.js): npm install -g @daisy/ace")
        )
        self.cancel_button.setEnabled(self._running)
        has_report = self._report is not None or self._ace_report is not None
        self.export_button.setEnabled(has_report and not self._running)

    def _help_html(self) -> str:
        """Buduje treść panelu pomocy (czego brakuje + jak zainstalować)."""
        java = self.tools.get("java")
        jar = self.tools.get("epubcheck")
        missing = []
        if not (java and java.available):
            missing.append(_("Java (Temurin JRE 17+)"))
        if not (jar and jar.available):
            missing.append("epubcheck.jar")
        return _(
            "<b>Walidacja wymaga dodatkowych narzędzi.</b><br>Brakuje: {missing}.<br><br>"
            "1. Zainstaluj <a href='https://adoptium.net/'>Temurin JRE 17+</a>.<br>"
            "2. Pobierz <a href='https://github.com/w3c/epubcheck/releases'>epubcheck-5.x</a>."
            "<br>3. Rozpakuj i wskaż <code>epubcheck.jar</code> przyciskiem poniżej."
        ).format(missing=", ".join(missing) or "—")

    def _pick_jar(self) -> None:
        """Pozwala wskazać plik epubcheck.jar; zapisuje override i ponawia detekcję."""
        path = open_file(self, _("Wskaż epubcheck.jar"), "", _("Plik JAR (*.jar)"))
        if path:
            self._set_tool_override("epubcheck_jar", path)

    def _pick_java(self) -> None:
        """Pozwala wskazać plik java(.exe); zapisuje override i ponawia detekcję."""
        path = open_file(self, _("Wskaż java.exe"), "", _("Plik wykonywalny Java (java*)"))
        if path:
            self._set_tool_override("java_path", path)

    def _set_tool_override(self, key: str, path: str) -> None:
        """Zapisuje override ścieżki w ``config['tools'][key]`` i wymusza re-detekcję.

        Ponowna detekcja jest WYMUSZONA (``force=True``), żeby stary zacache'owany
        wynik („brak narzędzia") nie blokował świeżo wskazanej ścieżki.
        """
        if self._config is not None:
            tools_section = self._config.get("tools")
            tools_section = tools_section if isinstance(tools_section, dict) else {}
            tools_section[key] = path
            self._config["tools"] = tools_section  # mark_dirty
            self._config.save_now()  # detect_with_cache czyta z dysku
            self.tools = detect_with_cache(self._config.path, force=True)
        else:
            self.tools = detect_with_cache(force=True)
        self._refresh_tools_state()

    # ── Uruchomienie walidacji ──────────────────────────────────────────────--

    def _run_check(self) -> None:
        """Waliduje zaznaczony plik w wątku roboczym."""
        epub_path = self.file_list.current_path()
        java = self.tools.get("java")
        jar = self.tools.get("epubcheck")
        if epub_path is None or self._running or not self._tools_ready():
            return
        assert java is not None and java.path is not None
        assert jar is not None and jar.path is not None

        self._running = True
        self._set_busy(True)
        self._refresh_actions()
        self.status_label.setText(_("Walidacja: {name}…").format(name=epub_path.name))
        self._worker = Worker(_run_check_worker, epub_path, java.path, jar.path)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.start()

    def _run_ace_check(self) -> None:
        """Audytuje dostępność zaznaczonego pliku w wątku roboczym (DAISY Ace)."""
        epub_path = self.file_list.current_path()
        ace = self.tools.get("ace")
        if epub_path is None or self._running or not self._ace_ready():
            return
        assert ace is not None and ace.path is not None

        self._running = True
        self._set_busy(True)
        self._refresh_actions()
        self.status_label.setText(_("Audyt dostępności: {name}…").format(name=epub_path.name))
        self._worker = Worker(_run_ace_worker, epub_path, ace.path)
        self._worker.done.connect(self._on_ace_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.start()

    def _cancel(self) -> None:
        """Zgłasza anulowanie trwającej walidacji (ubija proces Javy)."""
        if self._worker is not None and self._running:
            self.cancel_button.setEnabled(False)
            self.status_label.setText(_("Anulowanie…"))
            self._worker.cancel()

    def _set_busy(self, busy: bool) -> None:
        """Włącza/wyłącza nieokreślony pasek postępu (EpubCheck nie zna procentów)."""
        self.progress_bar.setRange(0, 0 if busy else 1)
        if not busy:
            self.progress_bar.setValue(0)

    def _on_done(self, result: object) -> None:
        """Odbiera raport EpubChecka z wątku i wypełnia drzewo."""
        self._running = False
        self._set_busy(False)
        report = cast(ValidationReport, result)
        self._report = report
        self._ace_report = None
        self._active_epub = report.epub_path
        self._rows = [_row_from_message(msg) for msg in report.messages]
        self._populate_tree()
        self._update_summary()
        verdict = _("POPRAWNY") if report.valid else _("NIEPOPRAWNY")
        self.status_label.setText(
            _("Zakończono w {sec:.1f}s — {verdict}").format(sec=report.duration_s, verdict=verdict)
        )
        self._refresh_actions()

    def _on_ace_done(self, result: object) -> None:
        """Odbiera raport Ace z wątku i wypełnia to samo drzewo wyników."""
        self._running = False
        self._set_busy(False)
        report = cast(AceReport, result)
        self._ace_report = report
        self._report = None
        self._active_epub = report.epub_path
        self._rows = [_row_from_ace(msg) for msg in report.messages]
        self._populate_tree()
        self._update_summary()
        verdict = _("DOSTĘPNY") if report.accessible else _("NIEDOSTĘPNY")
        self.status_label.setText(
            _("Audyt zakończono w {sec:.1f}s — {verdict}").format(
                sec=report.duration_s, verdict=verdict
            )
        )
        self._refresh_actions()

    def _on_cancelled(self) -> None:
        """Obsługuje anulowanie walidacji przez użytkownika."""
        self._running = False
        self._set_busy(False)
        self.status_label.setText(_("Anulowano"))
        self._refresh_actions()

    def _on_failed(self, message: str) -> None:
        """Obsługuje błąd techniczny walidacji (timeout, brak JSON itp.)."""
        self._running = False
        self._set_busy(False)
        self.status_label.setText(_("Walidacja nieudana: {error}").format(error=message))
        self._refresh_actions()

    # ── Drzewo wyników ──────────────────────────────────────────────────────--

    def _populate_tree(self) -> None:
        """Wypełnia drzewo wierszami z aktualnego raportu (z filtrami severity)."""
        self.tree.clear()
        items: list[QTreeWidgetItem] = []
        for row in self._rows:
            if not self._severity_visible(row.severity):
                continue
            items.append(self._make_item(row))
        self.tree.addTopLevelItems(items)

    def _severity_visible(self, severity: Severity) -> bool:
        """Czy dany poziom jest włączony w filtrach."""
        if severity in (Severity.FATAL, Severity.ERROR):
            return self.show_errors.isChecked()
        if severity == Severity.WARNING:
            return self.show_warnings.isChecked()
        return self.show_info.isChecked()

    def _make_item(self, row: _ResultRow) -> QTreeWidgetItem:
        """Buduje wiersz drzewa dla wyniku (kolor z motywu, dane w roli)."""
        where = row.internal_path or "—"
        if row.line is not None:
            where = f"{where}:{row.line}"
        item = QTreeWidgetItem([_severity_label(row.severity), row.code, where, row.message])
        color = QColor(_severity_color(row.severity, self._theme))
        for column in range(4):
            item.setForeground(column, color)
        item.setToolTip(3, row.message)
        item.setData(0, _LOCATION_ROLE, (row.internal_path, row.line))
        return item

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Dwuklik wiersza z lokalizacją otwiera plik w edytorze na danej linii."""
        location = item.data(0, _LOCATION_ROLE)
        if (
            not isinstance(location, tuple)
            or self._active_epub is None
            or self._main_window is None
        ):
            return
        internal_path, line = location
        if internal_path:
            self._main_window.open_in_editor(self._active_epub, internal_path, line)

    def _update_summary(self) -> None:
        """Aktualizuje pasek podsumowania (z formami mnogimi przez ngettext)."""
        if self._active_epub is None:
            self.summary_label.setText("")
            return
        counts: Counter[Severity] = Counter(row.severity for row in self._rows)
        errors = counts[Severity.FATAL] + counts[Severity.ERROR]
        warnings = counts[Severity.WARNING]
        infos = counts[Severity.INFO]
        errors_text = ngettext("{n} błąd", "{n} błędów", errors).format(n=errors)
        warnings_text = ngettext("{n} ostrzeżenie", "{n} ostrzeżeń", warnings).format(n=warnings)
        infos_text = ngettext("{n} informacja", "{n} informacji", infos).format(n=infos)
        self.summary_label.setText(
            f"✗ {errors_text}  ·  ⚠ {warnings_text}  ·  ℹ {infos_text}"  # noqa: RUF001
        )

    # ── Eksport ───────────────────────────────────────────────────────────────

    def _export_report(self) -> None:
        """Eksportuje aktywny raport (EpubCheck lub Ace) do JSON lub HTML."""
        if self._report is None and self._ace_report is None:
            return
        path = save_file(
            self, _("Eksport raportu"), "", _("JSON (*.json);;HTML (*.html)"), self._config
        )
        if not path:
            return
        target = Path(path)
        as_html = target.suffix.lower() == ".html"
        if self._ace_report is not None:
            content = (
                _ace_report_to_html(self._ace_report)
                if as_html
                else _ace_report_to_json(self._ace_report)
            )
        else:
            assert self._report is not None
            content = _report_to_html(self._report) if as_html else _report_to_json(self._report)
        try:
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            self.status_label.setText(_("Nie udało się zapisać: {error}").format(error=exc))
            return
        self.status_label.setText(_("Zapisano raport: {name}").format(name=target.name))

    # ── Motyw ─────────────────────────────────────────────────────────────────

    def set_theme(self, theme: Theme) -> None:
        """Aktualizuje motyw i przemalowuje wiersze drzewa."""
        self._theme = theme
        self._populate_tree()


def _severity_label(severity: Severity) -> str:
    """Lokalizowana etykieta poziomu istotności."""
    return {
        Severity.FATAL: _("Krytyczny"),
        Severity.ERROR: _("Błąd"),
        Severity.WARNING: _("Ostrzeżenie"),
        Severity.INFO: _("Informacja"),
    }[severity]


def _severity_color(severity: Severity, theme: Theme) -> str:
    """Kolor wiersza dla poziomu istotności (rola z palety kitu)."""
    if severity in (Severity.FATAL, Severity.ERROR):
        return theme.red
    if severity == Severity.WARNING:
        return theme.amber
    return theme.fg2


def _report_to_json(report: ValidationReport) -> str:
    """Serializuje raport do JSON (``dataclasses.asdict`` + ścieżki jako str)."""
    return json.dumps(dataclasses.asdict(report), ensure_ascii=False, indent=2, default=str)


def _report_to_html(report: ValidationReport) -> str:
    """Buduje samowystarczalną stronę HTML z tabelą komunikatów."""
    verdict = "valid" if report.valid else "INVALID"
    rows = "\n".join(
        f"<tr><td>{escape(message.severity.value)}</td><td>{escape(message.code)}</td><td>{escape(_location_text(message))}</td><td>{escape(message.message)}</td></tr>"
        for message in report.messages
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>EpubCheck — {escape(report.epub_path.name)}</title>"
        "<style>body{font-family:sans-serif}table{border-collapse:collapse;width:100%}"
        "td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}</style></head><body>"
        f"<h1>EpubCheck: {escape(report.epub_path.name)}</h1><p>{escape(verdict)} · {escape(report.epubcheck_version)}</p>"
        "<table><thead><tr><th>Severity</th><th>Code</th><th>Location</th><th>Message</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></body></html>"
    )


def _location_text(message: ValidationMessage) -> str:
    """Składa „ścieżka:linia" do eksportu (lub myślnik przy braku)."""
    where = message.internal_path or "—"
    return f"{where}:{message.line}" if message.line is not None else where


def _ace_report_to_json(report: AceReport) -> str:
    """Serializuje raport Ace do JSON (``dataclasses.asdict`` + ścieżki jako str)."""
    return json.dumps(dataclasses.asdict(report), ensure_ascii=False, indent=2, default=str)


def _ace_report_to_html(report: AceReport) -> str:
    """Buduje samowystarczalną stronę HTML z tabelą naruszeń dostępności."""
    verdict = "accessible" if report.accessible else "INACCESSIBLE"
    rows = "\n".join(
        f"<tr><td>{escape(message.severity.value)}</td><td>{escape(message.rule)}</td>"
        f"<td>{escape(message.internal_path or '—')}</td><td>{escape(message.message)}</td></tr>"
        for message in report.messages
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>DAISY Ace — {escape(report.epub_path.name)}</title>"
        "<style>body{font-family:sans-serif}table{border-collapse:collapse;width:100%}"
        "td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}</style></head><body>"
        f"<h1>DAISY Ace: {escape(report.epub_path.name)}</h1>"
        f"<p>{escape(verdict)} · {escape(report.ace_version)}</p>"
        "<table><thead><tr><th>Severity</th><th>Rule</th><th>Location</th><th>Message</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></body></html>"
    )


def _run_check_worker(
    _emit_line: EmitLine,
    _emit_progress: EmitProgress,
    should_cancel: ShouldCancel,
    epub_path: Path,
    java_path: Path,
    jar_path: Path,
) -> ValidationReport:
    """Uruchamia EpubCheck w wątku roboczym z możliwością anulowania.

    Błędy techniczne (:class:`ValidationError`) propagują się — :class:`Worker`
    zamienia je na sygnał ``failed`` (albo ``cancelled``, gdy zażądano anulowania)
    obsługiwany na pasku statusu.
    """
    return run_epubcheck(epub_path, java_path, jar_path, should_cancel=should_cancel)


def _run_ace_worker(
    _emit_line: EmitLine,
    _emit_progress: EmitProgress,
    should_cancel: ShouldCancel,
    epub_path: Path,
    ace_path: Path,
) -> AceReport:
    """Uruchamia DAISY Ace w wątku roboczym z możliwością anulowania.

    Błędy techniczne (:class:`ValidationError`) propagują się — :class:`Worker`
    zamienia je na sygnał ``failed`` (albo ``cancelled``, gdy zażądano anulowania).
    """
    return run_ace(epub_path, ace_path, should_cancel=should_cancel)
