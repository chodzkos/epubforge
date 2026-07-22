"""Zakładka „Walidacja" — EpubCheck z klikalnymi błędami skaczącymi do edytora.

Wynik walidacji renderujemy w :class:`QTreeWidget`; dwuklik wiersza z lokalizacją
woła ``MainWindow.open_in_editor`` (kontrakt F-C). Gdy brak Javy/epubcheck.jar,
zamiast wyników pokazujemy panel pomocy z instrukcją i wyborem jara.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from chodzkos_gui_kit.palette import Palette as Theme
from chodzkos_gui_kit.qt.dialogs import open_file
from chodzkos_gui_kit.qt.theme import current_palette as current_theme
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from epubforge.core import ConfigStore, Tool, detect_with_cache
from epubforge.gui.external_tools import ToolUnavailableError, launch_tool
from epubforge.gui.tabs.validator_reports import (
    ValidatorReportsMixin,
    _run_ace_worker,
    _run_check_worker,
)
from epubforge.gui.tabs.validator_results import (
    ResultRow,
    ValidatorResultsMixin,
    row_from_ace,
    row_from_message,
)
from epubforge.gui.widgets import (
    FileList,
    Section,
    file_list_count_label,
    file_list_texts,
    make_scrollable,
)
from epubforge.gui.widgets.horizontal_strip import HorizontalStrip
from epubforge.gui.workers import Worker
from epubforge.i18n import _
from epubforge.validators import (
    AceReport,
    ValidationReport,
)

if TYPE_CHECKING:
    from epubforge.gui.app import MainWindow

# Strony QStackedWidget: wyniki / panel pomocy (brak narzędzi).
_PAGE_RESULTS, _PAGE_HELP = 0, 1


class ValidatorTab(ValidatorReportsMixin, ValidatorResultsMixin, QWidget):
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
        self._rows: list[ResultRow] = []
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

        outer.addWidget(self._build_toolbar())

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

    def _build_toolbar(self) -> HorizontalStrip:
        strip = HorizontalStrip()
        toolbar = strip.row
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
        self.external_tool_buttons: dict[str, QPushButton] = {}
        for key, label in (("sigil", _("Sigil")), ("calibre_editor", _("Calibre Editor"))):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, tool_key=key: self._launch_tool(tool_key))
            toolbar.addWidget(button)
            self.external_tool_buttons[key] = button
        strip.finish()
        return strip

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
        self._refresh_external_tools()

    def _handoff_epub(self) -> Path | None:
        """Zwraca zaznaczony EPUB albo plik nadal opisywany przez raport."""
        return self.file_list.current_path() or self._active_epub

    def _refresh_external_tools(self) -> None:
        """Synchronizuje handoff ze stanem wyboru, walidacji i detekcji."""
        target = self._handoff_epub()
        for key, button in self.external_tool_buttons.items():
            label = _("Sigil") if key == "sigil" else _("Calibre Editor")
            tool = self.tools.get(key)
            available = bool(tool and tool.available and tool.path)
            button.setEnabled(target is not None and available and not self._running)
            if self._running:
                tooltip = _("Poczekaj na zakończenie walidacji przed otwarciem EPUB-a.")
            elif not available:
                tooltip = _("Nie wykryto {tool}").format(tool=label)
            elif target is None:
                tooltip = _("Najpierw zaznacz plik EPUB")
            else:
                assert tool is not None and tool.path is not None
                tooltip = _(
                    "Otwórz cały aktualny EPUB w {tool}. Program zobaczy wersję zapisaną "
                    "na dysku. Wykryta ścieżka: {path}"
                ).format(tool=label, path=tool.path)
            button.setToolTip(tooltip)

    def _launch_tool(self, key: str) -> None:
        """Otwiera cały bieżący EPUB przez wspólny helper narzędzi zewnętrznych."""
        label = _("Sigil") if key == "sigil" else _("Calibre Editor")
        target = self._handoff_epub()
        if target is None:
            self.status_label.setText(_("Najpierw zaznacz plik EPUB"))
            return
        try:
            launch_tool(self.tools.get(key), target)
        except ToolUnavailableError:
            self.status_label.setText(_("Nie wykryto {tool}").format(tool=label))
        except OSError as exc:
            message = _("Nie udało się uruchomić {tool}: {error}").format(tool=label, error=exc)
            self.status_label.setText(message)
            QMessageBox.critical(self, _("Błąd"), message)

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
        self._rows = [row_from_message(msg) for msg in report.messages]
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
        self._rows = [row_from_ace(msg) for msg in report.messages]
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
