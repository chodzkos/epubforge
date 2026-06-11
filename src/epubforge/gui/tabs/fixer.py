"""Zakładka GUI do naprawy plików EPUB (Qt)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from epubforge.core import Epub, Tool, Tools
from epubforge.fixers import CssFixOptions, HyphenationOptions, fix_css, hyphenate
from epubforge.fixers.hyphenator import HyphenationMethod
from epubforge.gui.widgets import FileList, LogView, Section
from epubforge.gui.workers import CREATE_NO_WINDOW, EmitLine, EmitProgress, Worker

logger = logging.getLogger(__name__)

_LANGUAGES = ["pl", "en", "en_US", "en_GB", "de", "fr", "es", "it", "cs", "uk"]

_METHOD_TOOLTIPS = {
    "soft-hyphen": (
        "Wstawia miękkie myślniki (\\u00ad) w tekście. Działa na KAŻDYM czytniku "
        "(też starym Kindle), ALE psuje słownik i wyszukiwarkę na czytniku."
    ),
    "css": ("Wstrzykuje regułę CSS 'hyphens: auto' — czysty tekst, ale słabo wspierane na Kindle."),
}


class FixerTab(QWidget):
    """Zakładka do hyphenacji i normalizacji CSS w plikach EPUB."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tools: dict[str, Tool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.tools = tools if tools is not None else {"calibre_viewer": Tools.calibre_viewer()}
        self.last_fixed_file: Path | None = None
        self._running = False
        self._worker: Worker | None = None

        self._build_layout()
        self._refresh_hyphen_warning()
        self._refresh_preview_button()

    # ── Budowa UI ─────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        """Buduje dwukolumnowy układ: pliki po lewej, opcje po prawej."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, stretch=1)

        left = QWidget()
        self._build_file_list(left)
        right = QWidget()
        self._build_right(right)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        self.status_label = QLabel("Dodaj pliki EPUB")
        outer.addWidget(self.status_label)

    def _build_file_list(self, parent: QWidget) -> None:
        """Buduje listę plików EPUB."""
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 10, 0)
        section = Section("Pliki EPUB")
        layout.addWidget(section)
        self.file_list = FileList(extensions={".epub"})
        self.file_list.files_changed.connect(self._on_files_changed)
        section.add_widget(self.file_list)

    def _build_right(self, parent: QWidget) -> None:
        """Buduje kolumnę opcji, logu i akcji."""
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)

        options = QHBoxLayout()
        options.addWidget(self._build_hyphenation_section(), stretch=1)
        options.addWidget(self._build_css_section(), stretch=1)
        layout.addLayout(options)

        self._build_log(layout)
        self._build_actions(layout)

    def _build_hyphenation_section(self) -> Section:
        """Buduje opcje dzielenia wyrazów."""
        section = Section("Hyphenation")

        self.hyphen_enabled = QCheckBox("Włącz")
        self.hyphen_enabled.setChecked(True)
        self.hyphen_enabled.setToolTip("Włącz dzielenie wyrazów dla wybranych EPUB")
        section.add_widget(self.hyphen_enabled)

        form = QFormLayout()
        section.content_layout().addLayout(form)
        self.hyphen_lang_box = QComboBox()
        self.hyphen_lang_box.addItems(_LANGUAGES)
        self.hyphen_lang_box.setCurrentText("pl")
        self.hyphen_lang_box.setToolTip("Język słownika dzielenia wyrazów (pyphen), np. pl, en_US")
        form.addRow("Język", self.hyphen_lang_box)

        methods = QVBoxLayout()
        self.hyphen_method_group = QButtonGroup(self)
        for value in ("soft-hyphen", "css"):
            radio = QRadioButton(value)
            radio.setToolTip(_METHOD_TOOLTIPS[value])
            radio.setProperty("method", value)
            if value == "soft-hyphen":
                radio.setChecked(True)
            radio.toggled.connect(self._refresh_hyphen_warning)
            self.hyphen_method_group.addButton(radio)
            methods.addWidget(radio)
        form.addRow("Metoda", self._wrap(methods))

        self.hyphen_warning_label = QLabel(
            "Soft-hyphen może psuć słownik i wyszukiwarkę na czytniku Kindle."
        )
        self.hyphen_warning_label.setWordWrap(True)
        section.add_widget(self.hyphen_warning_label)

        self.hyphen_skip_headers = QCheckBox("Pomiń nagłówki")
        self.hyphen_skip_headers.setChecked(True)
        self.hyphen_skip_headers.setToolTip("Nie dziel wyrazów w nagłówkach (h1-h3)")
        section.add_widget(self.hyphen_skip_headers)
        section.content_layout().addStretch(1)
        return section

    def _build_css_section(self) -> Section:
        """Buduje opcje normalizacji CSS."""
        section = Section("CSS Fixer")

        self.css_remove_colors = self._add_check(
            section,
            "Usuń kolory",
            checked=False,
            tooltip="Usuwa deklaracje color/background z CSS (czytnik narzuca własne)",
        )
        self.css_remove_fonts = self._add_check(
            section,
            "Usuń fonty",
            checked=False,
            tooltip="UWAGA: usuwa @font-face i pliki fontów z EPUB — nieodwracalne dla danej kopii",
        )
        self.css_inject_reset = self._add_check(
            section,
            "Dodaj reset CSS",
            checked=True,
            tooltip="Dodaje delikatny reset (marginesy/padding) dla spójnego renderowania",
        )
        self.css_replace_justify = self._add_check(
            section,
            "Zamień justowanie na lewe",
            checked=False,
            tooltip="Zamienia text-align: justify na left (mniej dużych odstępów)",
        )
        self.css_skip_hyphen_headers = self._add_check(
            section,
            "Wyłącz hyphenację nagłówków",
            checked=True,
            tooltip="Dodaje regułę CSS wyłączającą dzielenie wyrazów w nagłówkach",
        )

        margin = QHBoxLayout()
        self.css_book_margin = QCheckBox("Margines książki")
        self.css_book_margin.setToolTip("Wstrzykuje margines strony (w px) z pola obok")
        margin.addWidget(self.css_book_margin)
        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(0, 120)
        self.margin_spin.setValue(20)
        self.margin_spin.setToolTip("Szerokość marginesu strony w pikselach (0-120)")
        margin.addWidget(self.margin_spin)
        margin.addWidget(QLabel("px"))
        margin.addStretch(1)
        section.content_layout().addLayout(margin)
        section.content_layout().addStretch(1)
        return section

    def _build_log(self, layout: QVBoxLayout) -> None:
        """Buduje pole logu naprawy EPUB."""
        section = Section("Log")
        layout.addWidget(section, stretch=1)
        self.log_view = LogView()
        section.add_widget(self.log_view)

    def _build_actions(self, layout: QVBoxLayout) -> None:
        """Buduje przyciski uruchomienia i podglądu."""
        actions = QHBoxLayout()
        self.fix_button = QPushButton("Napraw")
        self.fix_button.setToolTip("Hyphenacja i naprawa CSS wybranych plików (zapis w miejscu).")
        self.fix_button.setEnabled(False)
        self.fix_button.clicked.connect(self._run_fix)
        actions.addWidget(self.fix_button)
        actions.addStretch(1)

        self.preview_button = QPushButton("Podgląd w Calibre Viewer")
        self.preview_button.setToolTip("Otwiera ostatni naprawiony EPUB w Calibre Viewer")
        self.preview_button.clicked.connect(self._view_result)
        actions.addWidget(self.preview_button)
        layout.addLayout(actions)

    def _add_check(self, section: Section, text: str, *, checked: bool, tooltip: str) -> QCheckBox:
        """Dodaje checkbox CSS do sekcji."""
        check = QCheckBox(text)
        check.setChecked(checked)
        check.setToolTip(tooltip)
        section.add_widget(check)
        return check

    def _wrap(self, layout: QVBoxLayout) -> QWidget:
        """Owija layout w widget (do osadzenia w QFormLayout)."""
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    # ── Logika ────────────────────────────────────────────────────────────────

    def _on_files_changed(self, files: list[Path]) -> None:
        """Aktualizuje stan przycisków po zmianie listy plików."""
        self.last_fixed_file = None
        self.fix_button.setEnabled(bool(files) and not self._running)
        self._refresh_preview_button()
        self._set_status(f"Wybrano {len(files)} {_plural_files(len(files))}")

    def _refresh_hyphen_warning(self) -> None:
        """Pokazuje ostrzeżenie tylko przy metodzie soft-hyphen."""
        self.hyphen_warning_label.setVisible(self._hyphen_method() == "soft-hyphen")

    def _hyphen_method(self) -> str:
        """Zwraca wybraną metodę dzielenia wyrazów."""
        button = self.hyphen_method_group.checkedButton()
        return cast(str, button.property("method")) if button is not None else "soft-hyphen"

    def _build_hyphen_options(self) -> HyphenationOptions | None:
        """Składa opcje hyphenacji z aktualnego stanu UI."""
        if not self.hyphen_enabled.isChecked():
            return None
        return HyphenationOptions(
            language=self.hyphen_lang_box.currentText(),
            method=cast(HyphenationMethod, self._hyphen_method()),
            skip_headers=self.hyphen_skip_headers.isChecked(),
        )

    def _build_css_options(self) -> CssFixOptions:
        """Składa opcje CSS fixer z aktualnego stanu UI."""
        return CssFixOptions(
            remove_colors=self.css_remove_colors.isChecked(),
            remove_fonts=self.css_remove_fonts.isChecked(),
            inject_reset=self.css_inject_reset.isChecked(),
            replace_justify="left" if self.css_replace_justify.isChecked() else "keep",
            inject_book_margin_px=self._book_margin_px(),
            skip_hyphenation_headers=self.css_skip_hyphen_headers.isChecked(),
        )

    def _book_margin_px(self) -> int | None:
        """Zwraca margines książki w px albo None, jeśli opcja jest wyłączona."""
        if not self.css_book_margin.isChecked():
            return None
        return max(0, self.margin_spin.value())

    def _run_fix(self) -> None:
        """Waliduje wejście i uruchamia naprawę w wątku roboczym."""
        if self._running:
            return
        files = self.file_list.files()
        if not files:
            self._set_status("Brak plików EPUB do naprawy")
            return

        self._running = True
        self.last_fixed_file = None
        self.fix_button.setEnabled(False)
        self.preview_button.setEnabled(False)
        self.log_view.clear()
        self._set_status("Naprawianie...")

        self._worker = Worker(
            _run_fix_worker, files, self._build_hyphen_options(), self._build_css_options()
        )
        self._worker.line.connect(self.log_view.append_line)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._finish_fix)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, current: int, total: int) -> None:
        """Aktualizuje status w trakcie batcha."""
        self._set_status(f"Naprawianie {current}/{total}")

    def _finish_fix(self, result: object) -> None:
        """Aktualizuje UI po zakończeniu pracy wątku."""
        succeeded, total, last_fixed = cast(tuple[int, int, Path | None], result)
        self._running = False
        self.last_fixed_file = last_fixed
        self.fix_button.setEnabled(bool(self.file_list.files()))
        self._refresh_preview_button()
        self._set_status(f"Zakończono: {succeeded}/{total} OK")

    def _on_failed(self, message: str) -> None:
        """Obsługuje nieoczekiwany błąd wątku naprawy."""
        self._running = False
        self.fix_button.setEnabled(bool(self.file_list.files()))
        self.log_view.append_line(f"BŁĄD: {message}", "err")
        self._set_status("Naprawa przerwana błędem")

    def _refresh_preview_button(self) -> None:
        """Włącza podgląd tylko po sukcesie i przy wykrytym Calibre Viewer."""
        self.preview_button.setEnabled(
            self.last_fixed_file is not None and self._viewer_tool() is not None
        )

    def _viewer_tool(self) -> Tool | None:
        """Zwraca dostępny Calibre Viewer albo None."""
        viewer = self.tools.get("calibre_viewer")
        if viewer is None or not viewer.available or viewer.path is None:
            return None
        return viewer

    def _view_result(self) -> None:
        """Otwiera ostatni naprawiony EPUB w Calibre Viewer."""
        viewer = self._viewer_tool()
        if self.last_fixed_file is None or viewer is None or viewer.path is None:
            self._set_status("Nie wykryto Calibre Viewer albo brak wyniku")
            return
        try:
            subprocess.Popen(
                [str(viewer.path), str(self.last_fixed_file)],
                creationflags=CREATE_NO_WINDOW,
            )
        except OSError as exc:
            self.log_view.append_line(f"BŁĄD: Nie udało się otworzyć podglądu: {exc}", "err")
            return
        self.log_view.append_line(f"Uruchomiono podgląd: {self.last_fixed_file.name}", "info")

    def _set_status(self, text: str) -> None:
        """Ustawia tekst paska statusu zakładki."""
        self.status_label.setText(text)


def _run_fix_worker(
    emit_line: EmitLine,
    emit_progress: EmitProgress,
    files: list[Path],
    hyphen_options: HyphenationOptions | None,
    css_options: CssFixOptions,
) -> tuple[int, int, Path | None]:
    """Naprawia pliki po kolei w wątku roboczym.

    Zwraca krotkę ``(udane, łącznie, ostatni_naprawiony)``.
    """
    succeeded = 0
    last_fixed: Path | None = None
    total = len(files)
    for index, path in enumerate(files, start=1):
        emit_progress(index, total)
        emit_line(f"→ {path.name}", "cmd")
        try:
            with Epub(path) as epub:
                if hyphen_options is not None:
                    emit_line("Hyphenation...", "info")
                    hyphenate(epub, hyphen_options)
                emit_line("CSS Fixer...", "info")
                fix_css(epub, css_options)
                last_fixed = epub.save()
        except Exception as exc:
            logger.exception("Nie udało się naprawić EPUB: %s", path)
            emit_line(f"BŁĄD: {exc}", "err")
            continue
        emit_line(f"OK: {last_fixed}", "ok")
        succeeded += 1
    return succeeded, total, last_fixed


def _plural_files(count: int) -> str:
    """Zwraca polską odmianę słowa plik dla licznika."""
    if count == 1:
        return "plik"
    if 2 <= count <= 4:
        return "pliki"
    return "plików"
