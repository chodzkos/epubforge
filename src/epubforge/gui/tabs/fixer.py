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
    QDialog,
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
from epubforge.fixers import (
    CssFixOptions,
    HyphenationOptions,
    PresetError,
    apply_preset,
    fix_css,
    get_preset,
    hyphenate,
    import_user_preset,
    list_presets,
)
from epubforge.fixers.hyphenator import HyphenationMethod
from epubforge.gui.file_dialogs import open_file
from epubforge.gui.theme import current_theme
from epubforge.gui.widgets import CssInspector, FileList, LogView, Section
from epubforge.gui.workers import CREATE_NO_WINDOW, EmitLine, EmitProgress, Worker
from epubforge.i18n import _, ngettext

logger = logging.getLogger(__name__)

_LANGUAGES = ["pl", "en", "en_US", "en_GB", "de", "fr", "es", "it", "cs", "uk"]


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

        self.status_label = QLabel(_("Dodaj pliki EPUB"))
        outer.addWidget(self.status_label)

    def _build_file_list(self, parent: QWidget) -> None:
        """Buduje listę plików EPUB."""
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 10, 0)
        section = Section(_("Pliki EPUB"))
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

        layout.addWidget(self._build_preset_section())
        self._build_log(layout)
        self._build_actions(layout)

    def _build_hyphenation_section(self) -> Section:
        """Buduje opcje dzielenia wyrazów."""
        section = Section(_("Dzielenie wyrazów"))

        self.hyphen_enabled = QCheckBox(_("Włącz"))
        self.hyphen_enabled.setChecked(True)
        self.hyphen_enabled.setToolTip(_("Włącz dzielenie wyrazów dla wybranych EPUB"))
        section.add_widget(self.hyphen_enabled)

        form = QFormLayout()
        section.content_layout().addLayout(form)
        self.hyphen_lang_box = QComboBox()
        self.hyphen_lang_box.addItems(_LANGUAGES)
        self.hyphen_lang_box.setCurrentText("pl")
        self.hyphen_lang_box.setToolTip(
            _("Język słownika dzielenia wyrazów (pyphen), np. pl, en_US")
        )
        form.addRow(_("Język"), self.hyphen_lang_box)

        methods = QVBoxLayout()
        self.hyphen_method_group = QButtonGroup(self)
        for value in ("soft-hyphen", "css"):
            radio = QRadioButton(value)
            radio.setToolTip(_method_tooltip(value))
            radio.setProperty("method", value)
            if value == "soft-hyphen":
                radio.setChecked(True)
            radio.toggled.connect(self._refresh_hyphen_warning)
            self.hyphen_method_group.addButton(radio)
            methods.addWidget(radio)
        form.addRow(_("Metoda"), self._wrap(methods))

        self.hyphen_warning_label = QLabel(
            _("Soft-hyphen może psuć słownik i wyszukiwarkę na czytniku Kindle.")
        )
        self.hyphen_warning_label.setWordWrap(True)
        section.add_widget(self.hyphen_warning_label)

        self.hyphen_skip_headers = QCheckBox(_("Pomiń nagłówki"))
        self.hyphen_skip_headers.setChecked(True)
        self.hyphen_skip_headers.setToolTip(_("Nie dziel wyrazów w nagłówkach (h1-h3)"))
        section.add_widget(self.hyphen_skip_headers)
        section.content_layout().addStretch(1)
        return section

    def _build_css_section(self) -> Section:
        """Buduje opcje normalizacji CSS."""
        section = Section(_("CSS Fixer"))

        self.css_remove_colors = self._add_check(
            section,
            _("Usuń kolory"),
            checked=False,
            tooltip=_("Usuwa deklaracje color/background z CSS (czytnik narzuca własne)"),
        )
        self.css_remove_fonts = self._add_check(
            section,
            _("Usuń fonty"),
            checked=False,
            tooltip=_(
                "UWAGA: usuwa @font-face i pliki fontów z EPUB — nieodwracalne dla danej kopii"
            ),
        )
        self.css_inject_reset = self._add_check(
            section,
            _("Dodaj reset CSS"),
            checked=True,
            tooltip=_("Dodaje delikatny reset (marginesy/padding) dla spójnego renderowania"),
        )
        self.css_replace_justify = self._add_check(
            section,
            _("Zamień justowanie na lewe"),
            checked=False,
            tooltip=_("Zamienia text-align: justify na left (mniej dużych odstępów)"),
        )
        self.css_skip_hyphen_headers = self._add_check(
            section,
            _("Wyłącz hyphenację nagłówków"),
            checked=True,
            tooltip=_("Dodaje regułę CSS wyłączającą dzielenie wyrazów w nagłówkach"),
        )

        margin = QHBoxLayout()
        self.css_book_margin = QCheckBox(_("Margines książki"))
        self.css_book_margin.setToolTip(_("Wstrzykuje margines strony (w px) z pola obok"))
        margin.addWidget(self.css_book_margin)
        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(0, 120)
        self.margin_spin.setValue(20)
        self.margin_spin.setToolTip(_("Szerokość marginesu strony w pikselach (0-120)"))
        margin.addWidget(self.margin_spin)
        margin.addWidget(QLabel("px"))
        margin.addStretch(1)
        section.content_layout().addLayout(margin)
        section.content_layout().addStretch(1)
        return section

    def _build_preset_section(self) -> Section:
        """Buduje sekcję wyboru i importu presetu CSS."""
        section = Section(_("Preset CSS"))

        self.preset_enabled = QCheckBox(_("Zastosuj preset"))
        self.preset_enabled.setToolTip(_("Dołącza wybrany arkusz stylów do EPUB podczas naprawy"))
        section.add_widget(self.preset_enabled)

        row = QHBoxLayout()
        self.preset_box = QComboBox()
        self.preset_box.setToolTip(_("Wbudowane presety oraz zaimportowane przez Ciebie"))
        self._populate_presets()
        row.addWidget(self.preset_box, stretch=1)

        self.preset_mode_group = QButtonGroup(self)
        for label, value in ((_("Dołącz"), "append"), (_("Zastąp"), "replace")):
            radio = QRadioButton(label)
            radio.setProperty("mode", value)
            radio.setToolTip(_preset_mode_tooltip(value))
            if value == "append":
                radio.setChecked(True)
            self.preset_mode_group.addButton(radio)
            row.addWidget(radio)

        self.preset_preview_button = QPushButton(_("Podgląd…"))
        self.preset_preview_button.setToolTip(_("Podejrzyj reguły presetu na przykładowym tekście"))
        self.preset_preview_button.clicked.connect(self._preview_preset)
        row.addWidget(self.preset_preview_button)

        self.preset_import_button = QPushButton(_("Importuj własny…"))
        self.preset_import_button.setToolTip(_("Zaimportuj własny plik .css jako preset"))
        self.preset_import_button.clicked.connect(self._import_preset)
        row.addWidget(self.preset_import_button)
        section.content_layout().addLayout(row)
        section.content_layout().addStretch(1)
        return section

    def _populate_presets(self, select_id: str | None = None) -> None:
        """Wypełnia listę presetów (nazwa — opis); opcjonalnie zaznacza ``select_id``."""
        self.preset_box.clear()
        for preset in list_presets():
            description = preset.display_description()
            label = (
                f"{preset.display_name()} — {description}" if description else preset.display_name()
            )
            self.preset_box.addItem(label, preset.id)
        if select_id is not None:
            index = self.preset_box.findData(select_id)
            if index >= 0:
                self.preset_box.setCurrentIndex(index)

    def _import_preset(self) -> None:
        """Importuje własny plik CSS jako preset i odświeża listę."""
        path = open_file(self, _("Importuj preset CSS"), "", _("Arkusze CSS (*.css)"))
        if not path:
            return
        try:
            preset = import_user_preset(Path(path))
        except PresetError as exc:
            self._set_status(_("Nie udało się zaimportować presetu: {error}").format(error=exc))
            return
        self._populate_presets(select_id=preset.id)
        self._set_status(_("Zaimportowano preset: {name}").format(name=preset.display_name()))

    def _preview_preset(self) -> None:
        """Otwiera podgląd reguł wybranego presetu (inspektor CSS tylko do odczytu)."""
        preset_id = self.preset_box.currentData()
        if not preset_id:
            return
        try:
            preset = get_preset(str(preset_id))
        except PresetError as exc:
            self._set_status(_("Nie udało się wczytać presetu: {error}").format(error=exc))
            return
        css = preset.read_css()
        dialog = QDialog(self)
        dialog.setWindowTitle(_("Podgląd presetu: {name}").format(name=preset.display_name()))
        dialog.resize(640, 560)
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            CssInspector(get_source=lambda: css, apply_replacement=None, theme=current_theme())
        )
        dialog.exec()

    def _preset_choice(self) -> tuple[str, str] | None:
        """Zwraca ``(id, tryb)`` wybranego presetu albo ``None``, gdy wyłączony."""
        if not self.preset_enabled.isChecked():
            return None
        preset_id = self.preset_box.currentData()
        if not preset_id:
            return None
        button = self.preset_mode_group.checkedButton()
        mode = cast(str, button.property("mode")) if button is not None else "append"
        return str(preset_id), mode

    def _build_log(self, layout: QVBoxLayout) -> None:
        """Buduje pole logu naprawy EPUB."""
        section = Section(_("Log"))
        layout.addWidget(section, stretch=1)
        self.log_view = LogView()
        section.add_widget(self.log_view)

    def _build_actions(self, layout: QVBoxLayout) -> None:
        """Buduje przyciski uruchomienia i podglądu."""
        actions = QHBoxLayout()
        self.fix_button = QPushButton(_("Napraw"))
        self.fix_button.setToolTip(
            _("Hyphenacja i naprawa CSS wybranych plików (zapis w miejscu).")
        )
        self.fix_button.setEnabled(False)
        self.fix_button.clicked.connect(self._run_fix)
        actions.addWidget(self.fix_button)
        actions.addStretch(1)

        self.preview_button = QPushButton(_("Podgląd w Calibre Viewer"))
        self.preview_button.setToolTip(_("Otwiera ostatni naprawiony EPUB w Calibre Viewer"))
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
        count = len(files)
        self._set_status(ngettext("Wybrano {n} plik", "Wybrano {n} plików", count).format(n=count))

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
            self._set_status(_("Brak plików EPUB do naprawy"))
            return

        self._running = True
        self.last_fixed_file = None
        self.fix_button.setEnabled(False)
        self.preview_button.setEnabled(False)
        self.log_view.clear()
        self._set_status(_("Naprawianie..."))

        self._worker = Worker(
            _run_fix_worker,
            files,
            self._build_hyphen_options(),
            self._build_css_options(),
            self._preset_choice(),
        )
        self._worker.line.connect(self.log_view.append_line)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._finish_fix)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, current: int, total: int) -> None:
        """Aktualizuje status w trakcie batcha."""
        self._set_status(_("Naprawianie {current}/{total}").format(current=current, total=total))

    def _finish_fix(self, result: object) -> None:
        """Aktualizuje UI po zakończeniu pracy wątku."""
        succeeded, total, last_fixed = cast(tuple[int, int, Path | None], result)
        self._running = False
        self.last_fixed_file = last_fixed
        self.fix_button.setEnabled(bool(self.file_list.files()))
        self._refresh_preview_button()
        self._set_status(_("Zakończono: {done}/{total} OK").format(done=succeeded, total=total))

    def _on_failed(self, message: str) -> None:
        """Obsługuje nieoczekiwany błąd wątku naprawy."""
        self._running = False
        self.fix_button.setEnabled(bool(self.file_list.files()))
        self.log_view.append_line(_("BŁĄD: {message}").format(message=message), "err")
        self._set_status(_("Naprawa przerwana błędem"))

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
            self._set_status(_("Nie wykryto Calibre Viewer albo brak wyniku"))
            return
        try:
            subprocess.Popen(
                [str(viewer.path), str(self.last_fixed_file)],
                creationflags=CREATE_NO_WINDOW,
            )
        except OSError as exc:
            self.log_view.append_line(
                _("BŁĄD: Nie udało się otworzyć podglądu: {error}").format(error=exc), "err"
            )
            return
        self.log_view.append_line(
            _("Uruchomiono podgląd: {name}").format(name=self.last_fixed_file.name), "info"
        )

    def _set_status(self, text: str) -> None:
        """Ustawia tekst paska statusu zakładki."""
        self.status_label.setText(text)


def _run_fix_worker(
    emit_line: EmitLine,
    emit_progress: EmitProgress,
    files: list[Path],
    hyphen_options: HyphenationOptions | None,
    css_options: CssFixOptions,
    preset_choice: tuple[str, str] | None,
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
                    emit_line(_("Hyphenation..."), "info")
                    hyphenate(epub, hyphen_options)
                emit_line(_("CSS Fixer..."), "info")
                fix_css(epub, css_options)
                if preset_choice is not None:
                    preset_id, preset_mode = preset_choice
                    emit_line(_("Preset CSS: {name}").format(name=preset_id), "info")
                    apply_preset(epub, get_preset(preset_id), mode=preset_mode)
                last_fixed = epub.save()
        except Exception as exc:
            logger.exception("Nie udało się naprawić EPUB: %s", path)
            emit_line(_("BŁĄD: {error}").format(error=exc), "err")
            continue
        emit_line(_("OK: {path}").format(path=last_fixed), "ok")
        succeeded += 1
    return succeeded, total, last_fixed


def _preset_mode_tooltip(value: str) -> str:
    """Zwraca tooltip trybu presetu jako literal gettext dla Babel."""
    if value == "replace":
        return _("Usuwa istniejące arkusze CSS z EPUB i wstawia tylko wybrany preset.")
    return _("Dodaje preset obok istniejących arkuszy (nadpisuje je kaskadą CSS).")


def _method_tooltip(value: str) -> str:
    """Zwraca tooltip metody dzielenia wyrazów jako literal gettext dla Babel."""
    if value == "css":
        return _(
            "Wstrzykuje regułę CSS 'hyphens: auto' — czysty tekst, ale słabo wspierane na Kindle."
        )
    return _(
        "Wstawia miękkie myślniki (\\u00ad) w tekście. Działa na KAŻDYM czytniku "
        "(też starym Kindle), ALE psuje słownik i wyszukiwarkę na czytniku."
    )
