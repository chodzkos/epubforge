"""Zakładka GUI eksportu EPUB do formatów Kindle (KFX/MOBI/AZW3) — Qt."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from epubforge.converters import KfxOptions, MobiOptions, to_kfx, to_mobi
from epubforge.converters.to_kfx import KfxEngine
from epubforge.converters.to_mobi import MobiEngine, MobiFormat
from epubforge.core import Tool
from epubforge.core.config import Config
from epubforge.gui.output import remember_output_dir, remembered_output_dir, resolve_output_dir
from epubforge.gui.widgets import (
    FileList,
    LogView,
    PathEntry,
    Section,
    file_list_count_label,
    file_list_texts,
    make_scrollable,
    path_entry_texts,
)
from epubforge.gui.workers import EmitLine, EmitProgress, Worker
from epubforge.i18n import _, ngettext

logger = logging.getLogger(__name__)


class KfxTab(QWidget):
    """Zakładka batchowego eksportu EPUB do KFX/MOBI/AZW3."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tools: dict[str, Tool] | None = None,
        config: Config | None = None,
    ) -> None:
        super().__init__(parent)
        self.tools = tools if tools is not None else {}
        self.config_data: Config = config if config is not None else {}
        self._running = False
        self._worker: Worker | None = None

        self._build_layout()
        self._on_format_change()

        remembered = remembered_output_dir(self.config_data)
        if remembered:
            self.output_dir.set(remembered)

    # ── Budowa UI ─────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        """Buduje dwukolumnowy układ: pliki po lewej, opcje po prawej."""
        content = QWidget()
        outer = QVBoxLayout(content)
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

        self._build_status(outer)
        outer.addStretch(1)

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(make_scrollable(content))
        self.setLayout(root)

    def _build_file_list(self, parent: QWidget) -> None:
        """Buduje listę plików EPUB."""
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 10, 0)
        section = Section(_("Pliki EPUB"))
        layout.addWidget(section)
        self.file_list = FileList(
            extensions={".epub"},
            config=self.config_data,
            texts=file_list_texts(),
            count_label=file_list_count_label,
        )
        self.file_list.files_changed.connect(self._on_files_changed)
        section.add_widget(self.file_list)

    def _build_right(self, parent: QWidget) -> None:
        """Buduje kolumnę formatu, silników, opcji, logu i akcji."""
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        self._build_format_section(layout)
        self._build_engine_sections(layout)
        self._build_options_section(layout)
        self._build_log(layout)
        self._build_actions(layout)

    def _build_format_section(self, layout: QVBoxLayout) -> None:
        """Buduje wybór formatu docelowego (KFX / MOBI / AZW3)."""
        section = Section(_("Format docelowy"))
        layout.addWidget(section)
        row = QHBoxLayout()
        self.format_group = QButtonGroup(self)
        for value, label in (("kfx", "KFX"), ("mobi", "MOBI"), ("azw3", "AZW3")):
            radio = QRadioButton(label)
            radio.setToolTip(_format_tooltip(value))
            radio.setProperty("fmt", value)
            if value == "kfx":
                radio.setChecked(True)
            radio.toggled.connect(self._on_format_change)
            self.format_group.addButton(radio)
            row.addWidget(radio)
        row.addStretch(1)
        section.content_layout().addLayout(row)

    def _build_engine_sections(self, layout: QVBoxLayout) -> None:
        """Buduje sekcje silników (KFX i MOBI) — widoczna jest jedna naraz."""
        self.kfx_engine_section = self._build_kfx_engine_section()
        self.mobi_engine_section = self._build_mobi_engine_section()
        layout.addWidget(self.kfx_engine_section)
        layout.addWidget(self.mobi_engine_section)

    def _build_kfx_engine_section(self) -> Section:
        """Buduje sekcję wyboru silnika KFX."""
        section = Section(_("Silnik KFX"))
        self.kfx_engine_group = QButtonGroup(self)

        calibre = QRadioButton(_("Calibre + wtyczka KFX"))
        calibre.setToolTip(_("Zalecany silnik KFX — Calibre z wtyczką KFX Output"))
        calibre.setProperty("engine", "calibre")
        calibre.setChecked(True)
        calibre.toggled.connect(self._refresh_kp3_warning)
        self.kfx_engine_group.addButton(calibre)
        section.content_layout().addLayout(self._engine_row(calibre, _("ZALECANE")))

        kp3 = QRadioButton("Kindle Previewer 3")
        kp3.setToolTip(
            _(
                "Eksperymentalny silnik KFX — wrażliwy na nieidealny EPUB. "
                "Preferuj Calibre + wtyczkę KFX Output."
            )
        )
        kp3.setProperty("engine", "kindle-previewer")
        kp3.toggled.connect(self._refresh_kp3_warning)
        self.kfx_engine_group.addButton(kp3)
        section.content_layout().addLayout(
            self._engine_row(kp3, _("EKSPERYMENTALNE - wrażliwe na formatowanie"))
        )

        self.kp3_warning = QLabel(_kp3_warning())
        self.kp3_warning.setWordWrap(True)
        section.add_widget(self.kp3_warning)
        return section

    def _build_mobi_engine_section(self) -> Section:
        """Buduje sekcję wyboru silnika MOBI/AZW3."""
        section = Section(_("Silnik MOBI/AZW3"))
        self.mobi_engine_group = QButtonGroup(self)

        calibre = QRadioButton("Calibre ebook-convert")
        calibre.setToolTip(_("Zalecany silnik MOBI/AZW3 — nowoczesny i aktywnie rozwijany"))
        calibre.setProperty("engine", "calibre")
        calibre.setChecked(True)
        calibre.toggled.connect(self._refresh_kindlegen_warning)
        self.mobi_engine_group.addButton(calibre)
        section.content_layout().addLayout(self._engine_row(calibre, _("ZALECANE")))

        kindlegen = QRadioButton("kindlegen")
        kindlegen.setToolTip(
            _(
                "Wycofany przez Amazon (utknął na 2.9). Działa do MOBI, ale "
                "zalecany jest Calibre ebook-convert."
            )
        )
        kindlegen.setProperty("engine", "kindlegen")
        kindlegen.toggled.connect(self._refresh_kindlegen_warning)
        self.mobi_engine_group.addButton(kindlegen)
        section.content_layout().addLayout(self._engine_row(kindlegen, _("WYCOFANY - opcjonalny")))

        self.kindlegen_warning = QLabel(_kindlegen_warning())
        self.kindlegen_warning.setWordWrap(True)
        section.add_widget(self.kindlegen_warning)
        return section

    def _engine_row(self, radio: QRadioButton, badge: str) -> QHBoxLayout:
        """Buduje wiersz: radiobutton + etykieta-status (badge)."""
        row = QHBoxLayout()
        row.addWidget(radio)
        row.addWidget(QLabel(badge))
        row.addStretch(1)
        return row

    def _build_options_section(self, layout: QVBoxLayout) -> None:
        """Buduje pozostałe opcje konwersji."""
        section = Section(_("Opcje"))
        layout.addWidget(section)

        self.fix_epub_check = QCheckBox(_("Napraw EPUB przed konwersją"))
        self.fix_epub_check.setChecked(True)
        self.fix_epub_check.setToolTip(
            _("Przed eksportem uruchamia podstawową naprawę CSS (zalecane)")
        )
        section.add_widget(self.fix_epub_check)

        form = QFormLayout()
        section.content_layout().addLayout(form)
        self.output_dir = PathEntry(
            mode="dir",
            config=self.config_data,
            remember_key="last_output_dir",
            texts=path_entry_texts(),
        )
        self.output_dir.entry.setToolTip(
            _("Folder na pliki wynikowe; puste = zapis obok pliku źródłowego")
        )
        form.addRow(_("Folder wyjściowy"), self.output_dir)

    def _build_log(self, layout: QVBoxLayout) -> None:
        """Buduje pole logu konwersji."""
        section = Section(_("Log"))
        layout.addWidget(section, stretch=1)
        self.log_view = LogView()
        section.add_widget(self.log_view)

    def _build_actions(self, layout: QVBoxLayout) -> None:
        """Buduje przycisk konwersji."""
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.convert_button = QPushButton(_("Konwertuj"))
        self.convert_button.setToolTip(
            _(
                "Eksportuje wybrane pliki EPUB do wybranego formatu Kindle "
                "(KFX/MOBI/AZW3). Puste pole folderu = zapis obok źródła."
            )
        )
        self.convert_button.setEnabled(False)
        self.convert_button.clicked.connect(self._run_conversion)
        actions.addWidget(self.convert_button)
        layout.addLayout(actions)

    def _build_status(self, layout: QVBoxLayout) -> None:
        """Buduje pasek statusu i postępu batch processing."""
        row = QHBoxLayout()
        self.status_label = QLabel(_("Dodaj pliki EPUB"))
        row.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        row.addWidget(self.progress_bar, stretch=1)
        layout.addLayout(row)

    # ── Reakcje UI ──────────────────────────────────────────────────────────────

    def _current_format(self) -> str:
        """Zwraca wybrany format docelowy (kfx/mobi/azw3)."""
        button = self.format_group.checkedButton()
        return cast(str, button.property("fmt")) if button is not None else "kfx"

    def _on_format_change(self) -> None:
        """Pokazuje sekcję silnika właściwą dla wybranego formatu."""
        fmt = self._current_format()
        is_kfx = fmt == "kfx"
        self.kfx_engine_section.setVisible(is_kfx)
        self.mobi_engine_section.setVisible(not is_kfx)
        if is_kfx:
            self._refresh_kp3_warning()
        else:
            self._refresh_kindlegen_warning()
        self.convert_button.setText(_("Konwertuj do {format}").format(format=fmt.upper()))

    def _on_files_changed(self, files: list[Path]) -> None:
        """Aktualizuje przycisk i podpowiada katalog wyjściowy, gdy pole puste."""
        self.convert_button.setEnabled(bool(files) and not self._running)
        count = len(files)
        self._set_status(
            ngettext("Wybrano {n} plik EPUB", "Wybrano {n} plików EPUB", count).format(n=count)
        )
        if files and not self.output_dir.get().strip():
            self.output_dir.set(str(files[0].parent))

    def _kfx_engine(self) -> KfxEngine:
        """Zwraca wybrany silnik KFX."""
        button = self.kfx_engine_group.checkedButton()
        return cast(KfxEngine, button.property("engine")) if button is not None else "calibre"

    def _mobi_engine(self) -> MobiEngine:
        """Zwraca wybrany silnik MOBI/AZW3."""
        button = self.mobi_engine_group.checkedButton()
        return cast(MobiEngine, button.property("engine")) if button is not None else "calibre"

    def _refresh_kp3_warning(self) -> None:
        """Pokazuje porady przy eksperymentalnym KP3 (tylko w trybie KFX)."""
        self.kp3_warning.setVisible(
            self._current_format() == "kfx" and self._kfx_engine() == "kindle-previewer"
        )

    def _refresh_kindlegen_warning(self) -> None:
        """Pokazuje ostrzeżenie przy wybraniu wycofanego kindlegen."""
        self.kindlegen_warning.setVisible(
            self._current_format() != "kfx" and self._mobi_engine() == "kindlegen"
        )

    # ── Logika konwersji ─────────────────────────────────────────────────────────

    def _build_options_obj(self) -> KfxOptions:
        """Składa KfxOptions z aktualnego stanu formularza."""
        return KfxOptions(engine=self._kfx_engine(), fix_epub_first=self.fix_epub_check.isChecked())

    def _build_mobi_options(self) -> MobiOptions:
        """Składa MobiOptions z aktualnego stanu formularza."""
        return MobiOptions(
            fmt=cast(MobiFormat, self._current_format()),
            engine=self._mobi_engine(),
            fix_epub_first=self.fix_epub_check.isChecked(),
        )

    def _run_conversion(self) -> None:
        """Waliduje formularz i uruchamia konwersję w wątku roboczym."""
        if self._running:
            return
        files = self.file_list.files()
        if not files:
            self._set_status(_("Brak plików EPUB do konwersji"))
            return
        output = self.output_dir.get().strip()

        self._running = True
        self.convert_button.setEnabled(False)
        self.log_view.clear()
        self.progress_bar.setRange(0, len(files))
        self.progress_bar.setValue(0)
        self._set_status(_("Konwersja trwa..."))

        remember_output_dir(self.config_data, output)
        output_dir = Path(output) if output else None
        if self._current_format() == "kfx":
            self._worker = Worker(_run_kfx_worker, files, output_dir, self._build_options_obj())
        else:
            self._worker = Worker(_run_mobi_worker, files, output_dir, self._build_mobi_options())
        self._worker.line.connect(self.log_view.append_line)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._finish_conversion)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, current: int, total: int) -> None:
        """Aktualizuje pasek postępu i status."""
        self.progress_bar.setValue(current)
        self._set_status(_("Konwersja {current}/{total}").format(current=current, total=total))

    def _finish_conversion(self, result: object) -> None:
        """Aktualizuje UI po zakończeniu konwersji."""
        succeeded, total = cast(tuple[int, int], result)
        self._running = False
        self.convert_button.setEnabled(bool(self.file_list.files()))
        self._set_status(_("Zakończono: {done}/{total} OK").format(done=succeeded, total=total))

    def _on_failed(self, message: str) -> None:
        """Obsługuje nieoczekiwany błąd wątku konwersji."""
        self._running = False
        self.convert_button.setEnabled(bool(self.file_list.files()))
        self.log_view.append_line(_("BŁĄD: {message}").format(message=message), "err")
        self._set_status(_("Konwersja przerwana błędem"))

    def _set_status(self, text: str) -> None:
        """Ustawia tekst paska statusu zakładki."""
        self.status_label.setText(text)


def _run_kfx_worker(
    emit_line: EmitLine,
    emit_progress: EmitProgress,
    files: list[Path],
    target_dir: Path | None,
    options: KfxOptions,
) -> tuple[int, int]:
    """Konwertuje pliki do KFX po kolei. Zwraca ``(udane, łącznie)``."""
    succeeded = 0
    total = len(files)
    for index, source in enumerate(files, start=1):
        emit_line(f"→ {source.name}", "cmd")
        try:
            result = to_kfx(source, resolve_output_dir(target_dir, source), options)
        except Exception as exc:
            logger.exception("Błąd konwersji KFX: %s", source)
            emit_line(_("BŁĄD: {error}").format(error=exc), "err")
        else:
            if result.log:
                emit_line(result.log, "info")
            emit_line(
                _("OK [{engine}]: {name}").format(
                    engine=result.engine, name=result.output_path.name
                ),
                "ok",
            )
            succeeded += 1
        emit_progress(index, total)
    return succeeded, total


def _run_mobi_worker(
    emit_line: EmitLine,
    emit_progress: EmitProgress,
    files: list[Path],
    target_dir: Path | None,
    options: MobiOptions,
) -> tuple[int, int]:
    """Konwertuje pliki do MOBI/AZW3 po kolei. Zwraca ``(udane, łącznie)``."""
    succeeded = 0
    total = len(files)
    for index, source in enumerate(files, start=1):
        emit_line(f"→ {source.name}", "cmd")
        target = resolve_output_dir(target_dir, source) / f"{source.stem}.{options.fmt}"
        try:
            result = to_mobi(source, target, options)
        except Exception as exc:
            logger.exception("Błąd konwersji MOBI/AZW3: %s", source)
            emit_line(_("BŁĄD: {error}").format(error=exc), "err")
        else:
            if result.log:
                emit_line(result.log, "info")
            emit_line(
                _("OK [{engine}]: {name}").format(
                    engine=result.engine, name=result.output_path.name
                ),
                "ok",
            )
            succeeded += 1
        emit_progress(index, total)
    return succeeded, total


def _format_tooltip(value: str) -> str:
    """Zwraca tooltip formatu docelowego jako literal gettext dla Babel."""
    if value == "mobi":
        return _("MOBI — starszy, uniwersalny format Kindle")
    if value == "azw3":
        return _("AZW3 — format Kindle KF8 (Calibre)")
    return _("KFX — nowoczesny format Kindle (Calibre + wtyczka KFX Output)")


def _kp3_warning() -> str:
    """Zwraca ostrzeżenie dla Kindle Previewer 3."""
    return _(
        "Kindle Previewer 3 jest eksperymentalny i bardziej wrażliwy na błędy EPUB. "
        "Przed konwersją usuń niestandardowe fonty, uprość CSS, unikaj wymuszonych "
        "marginesów i zostaw włączoną naprawę EPUB. Jeśli konwersja się nie powiedzie, "
        "wróć do silnika Calibre + wtyczka KFX Output."
    )


def _kindlegen_warning() -> str:
    """Zwraca ostrzeżenie dla kindlegen."""
    return _(
        "kindlegen jest oficjalnie wycofany przez Amazon (utknął na wersji 2.9) i nie "
        "jest już rozwijany. Nadal tworzy poprawne pliki MOBI, ale zalecanym, "
        "nowocześniejszym silnikiem jest Calibre ebook-convert."
    )
