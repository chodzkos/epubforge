"""Zakładka „Walidacja" — EpubCheck z klikalnymi błędami skaczącymi do edytora.

Wynik walidacji renderujemy w :class:`QTreeWidget`; dwuklik wiersza z lokalizacją
woła ``MainWindow.open_in_editor`` (kontrakt F-C). Gdy brak Javy/epubcheck.jar,
zamiast wyników pokazujemy panel pomocy z instrukcją i wyborem jara.
"""

from __future__ import annotations

import dataclasses
import json
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
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from epubforge.core import ConfigStore, Tool, detect_with_cache
from epubforge.gui.widgets import FileList, Section
from epubforge.gui.workers import EmitLine, EmitProgress, Worker
from epubforge.i18n import _, ngettext
from epubforge.validators import Severity, ValidationMessage, ValidationReport, run_epubcheck

if TYPE_CHECKING:
    from epubforge.gui.app import MainWindow

# Strony QStackedWidget: wyniki / panel pomocy (brak narzędzi).
_PAGE_RESULTS, _PAGE_HELP = 0, 1
# Lokalizacja w wierszu drzewa: krotka ``(internal_path, line)`` pod jedną rolą.
_LOCATION_ROLE = Qt.ItemDataRole.UserRole


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
        self._running = False
        self._worker: Worker | None = None

        self._build_ui()
        self._refresh_tools_state()

    # ── Budowa UI ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        section = Section(_("Pliki EPUB"))
        self.file_list = FileList(extensions={".epub"}, config=self._config)
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

    def _build_toolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        self.check_button = QPushButton(_("Sprawdź zaznaczony"))
        self.check_button.setToolTip(_("Uruchom EpubCheck na zaznaczonym pliku"))
        self.check_button.clicked.connect(self._run_check)
        toolbar.addWidget(self.check_button)
        toolbar.addStretch(1)
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

    def _refresh_tools_state(self) -> None:
        """Pokazuje wyniki albo panel pomocy zależnie od dostępności narzędzi."""
        ready = self._tools_ready()
        self.stack.setCurrentIndex(_PAGE_RESULTS if ready else _PAGE_HELP)
        if not ready:
            self.help_label.setText(self._help_html())
        self._refresh_actions()

    def _refresh_actions(self) -> None:
        """Aktualizuje stan przycisków (zależnie od narzędzi, pliku, trwającej pracy)."""
        can_check = (
            self._tools_ready() and self.file_list.current_path() is not None and not self._running
        )
        self.check_button.setEnabled(can_check)
        self.export_button.setEnabled(self._report is not None and not self._running)

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
        self._refresh_actions()
        self.status_label.setText(_("Walidacja: {name}…").format(name=epub_path.name))
        self._worker = Worker(_run_check_worker, epub_path, java.path, jar.path)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, result: object) -> None:
        """Odbiera raport z wątku i wypełnia drzewo."""
        self._running = False
        self._report = cast(ValidationReport, result)
        self._populate_tree()
        self._update_summary()
        verdict = _("POPRAWNY") if self._report.valid else _("NIEPOPRAWNY")
        self.status_label.setText(
            _("Zakończono w {sec:.1f}s — {verdict}").format(
                sec=self._report.duration_s, verdict=verdict
            )
        )
        self._refresh_actions()

    def _on_failed(self, message: str) -> None:
        """Obsługuje błąd techniczny walidacji (timeout, brak JSON itp.)."""
        self._running = False
        self.status_label.setText(_("Walidacja nieudana: {error}").format(error=message))
        self._refresh_actions()

    # ── Drzewo wyników ──────────────────────────────────────────────────────--

    def _populate_tree(self) -> None:
        """Wypełnia drzewo komunikatami z aktualnego raportu (z filtrami severity)."""
        self.tree.clear()
        if self._report is None:
            return
        items: list[QTreeWidgetItem] = []
        for message in self._report.messages:
            if not self._severity_visible(message.severity):
                continue
            items.append(self._make_item(message))
        self.tree.addTopLevelItems(items)

    def _severity_visible(self, severity: Severity) -> bool:
        """Czy dany poziom jest włączony w filtrach."""
        if severity in (Severity.FATAL, Severity.ERROR):
            return self.show_errors.isChecked()
        if severity == Severity.WARNING:
            return self.show_warnings.isChecked()
        return self.show_info.isChecked()

    def _make_item(self, message: ValidationMessage) -> QTreeWidgetItem:
        """Buduje wiersz drzewa dla komunikatu (kolor z motywu, dane w roli)."""
        where = message.internal_path or "—"
        if message.line is not None:
            where = f"{where}:{message.line}"
        item = QTreeWidgetItem(
            [_severity_label(message.severity), message.code, where, message.message]
        )
        color = QColor(_severity_color(message.severity, self._theme))
        for column in range(4):
            item.setForeground(column, color)
        item.setToolTip(3, message.message)
        item.setData(0, _LOCATION_ROLE, (message.internal_path, message.line))
        return item

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Dwuklik wiersza z lokalizacją otwiera plik w edytorze na danej linii."""
        location = item.data(0, _LOCATION_ROLE)
        if not isinstance(location, tuple) or self._report is None or self._main_window is None:
            return
        internal_path, line = location
        if internal_path:
            self._main_window.open_in_editor(self._report.epub_path, internal_path, line)

    def _update_summary(self) -> None:
        """Aktualizuje pasek podsumowania (z formami mnogimi przez ngettext)."""
        if self._report is None:
            self.summary_label.setText("")
            return
        counts = self._report.counts()
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
        """Eksportuje raport do JSON lub HTML (wg rozszerzenia wybranego pliku)."""
        if self._report is None:
            return
        path = save_file(
            self, _("Eksport raportu"), "", _("JSON (*.json);;HTML (*.html)"), self._config
        )
        if not path:
            return
        target = Path(path)
        try:
            if target.suffix.lower() == ".html":
                target.write_text(_report_to_html(self._report), encoding="utf-8")
            else:
                target.write_text(_report_to_json(self._report), encoding="utf-8")
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
    # str(...) zawęża pole palety kitu (bez py.typed w v0.1.0 mypy widzi Any).
    if severity in (Severity.FATAL, Severity.ERROR):
        return str(theme.red)
    if severity == Severity.WARNING:
        return str(theme.amber)
    return str(theme.fg2)


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


def _run_check_worker(
    _emit_line: EmitLine,
    _emit_progress: EmitProgress,
    epub_path: Path,
    java_path: Path,
    jar_path: Path,
) -> ValidationReport:
    """Uruchamia EpubCheck w wątku roboczym.

    Błędy techniczne (:class:`ValidationError`) propagują się — :class:`Worker`
    zamienia je na sygnał ``failed`` obsługiwany na pasku statusu.
    """
    return run_epubcheck(epub_path, java_path, jar_path)
