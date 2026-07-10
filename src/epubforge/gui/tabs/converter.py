"""Zakładka konwersji formatów wejściowych do EPUB (Qt)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from epubforge.converters import (
    KINDLE_INPUT_EXTENSIONS,
    SUPPORTED_INPUT_EXTENSIONS,
    ConvertOptions,
    has_kindle_drm,
    to_epub_streaming,
)
from epubforge.converters.to_epub import Engine
from epubforge.core import Metadata, Tool
from epubforge.core.config import Config
from epubforge.core.detection import Tools
from epubforge.core.exceptions import ConversionError, ConverterNotFoundError
from epubforge.gui.external_tools import ToolUnavailableError, launch_tool
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
from epubforge.gui.workers import EmitLine, EmitProgress, ShouldCancel, Worker
from epubforge.i18n import _

# Najczęstsze kody języków dla dropdownu (kolejność = priorytet wyświetlania).
_LANGUAGES = ["pl", "en", "de", "fr", "es", "it", "ru", "cs", "uk", "nl", "pt"]


class ConverterTab(QWidget):
    """Zakładka konwersji TXT/DOCX/HTML/MD/PDF… → EPUB."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        config: Config | None = None,
        tools: dict[str, Tool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.config_data: Config = config if config is not None else {}
        self.tools: dict[str, Tool] = tools if tools is not None else _detect_tools()
        self._converting = False
        self._worker: Worker | None = None

        self._build_layout()

        remembered = remembered_output_dir(self.config_data)
        if remembered:
            self.output_entry.set(remembered)

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

        status_row = QHBoxLayout()
        self.status_label = QLabel(_("Dodaj pliki wejściowe"))
        status_row.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        status_row.addWidget(self.progress_bar, stretch=1)
        outer.addLayout(status_row)
        outer.addStretch(1)

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(make_scrollable(content))
        self.setLayout(root)

    def _build_file_list(self, parent: QWidget) -> None:
        """Buduje listę plików wejściowych z potwierdzeniem PDF."""
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 10, 0)
        section = Section(_("Pliki wejściowe"))
        layout.addWidget(section)
        self.file_list = FileList(
            extensions=SUPPORTED_INPUT_EXTENSIONS,
            confirm=self._confirm_file,
            config=self.config_data,
            texts=file_list_texts(),
            count_label=file_list_count_label,
        )
        self.file_list.files_changed.connect(self._on_files_changed)
        section.add_widget(self.file_list)

    def _build_right(self, parent: QWidget) -> None:
        """Buduje kolumnę opcji i logu."""
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        self._build_options(layout)
        self._build_log(layout)

    def _build_options(self, layout: QVBoxLayout) -> None:
        """Buduje formularz metadanych, okładki, silnika i wyjścia."""
        section = Section(_("Opcje konwersji"))
        layout.addWidget(section)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        section.content_layout().addLayout(form)

        self.title_edit = QLineEdit()
        self.title_edit.setToolTip(_("Tytuł książki w wynikowym EPUB (opcjonalny)"))
        form.addRow(_("Tytuł"), self.title_edit)

        self.author_edit = QLineEdit()
        self.author_edit.setToolTip(_("Autor; zalecany format: Nazwisko, Imię (opcjonalny)"))
        form.addRow(_("Autor"), self.author_edit)

        self.language_box = QComboBox()
        self.language_box.addItems(_LANGUAGES)
        self.language_box.setCurrentText("pl")
        self.language_box.setToolTip(_("Kod języka treści, np. pl, en, de"))
        form.addRow(_("Język"), self.language_box)

        self.cover_entry = PathEntry(
            mode="file",
            filetypes=[(_("Obrazy"), "*.jpg *.jpeg *.png *.gif"), (_("Wszystkie pliki"), "*.*")],
            texts=path_entry_texts(),
        )
        self.cover_entry.entry.setToolTip(_("Opcjonalny obraz okładki (jpg/png/gif)"))
        form.addRow(_("Okładka"), self.cover_entry)

        form.addRow(_("Silnik"), self._build_engine_row())

        self.kindle_notice = QLabel(_("Pliki Kindle (MOBI/AZW3) wymagają Calibre."))
        self.kindle_notice.setWordWrap(True)
        self.kindle_notice.setVisible(False)
        section.content_layout().addWidget(self.kindle_notice)

        self.output_entry = PathEntry(
            mode="dir",
            config=self.config_data,
            remember_key="last_output_dir",
            texts=path_entry_texts(),
        )
        self.output_entry.entry.setToolTip(
            _("Folder na pliki .epub; puste = zapis obok pliku źródłowego")
        )
        form.addRow(_("Folder wyjściowy"), self.output_entry)

        actions = QHBoxLayout()
        self.convert_button = QPushButton(_("Konwertuj"))
        self.convert_button.setToolTip(
            _(
                "Konwertuje wybrane pliki do EPUB wybranym silnikiem.\n"
                "Puste pole 'Folder wyjściowy' = zapis obok pliku źródłowego."
            )
        )
        self.convert_button.clicked.connect(self._convert)
        actions.addWidget(self.convert_button)
        self.cancel_button = QPushButton(_("Anuluj"))
        self.cancel_button.setToolTip(_("Przerywa trwającą konwersję (kończy proces silnika)"))
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        actions.addWidget(self.cancel_button)
        self.pdf2md_button = QPushButton(_("Otwórz w pdf2md"))
        self.pdf2md_button.setToolTip(_("Otwiera wybrany PDF w aplikacji pdf2md (GUI)"))
        self.pdf2md_button.clicked.connect(self._open_in_pdf2md)
        # Handoff widoczny tylko, gdy wykryto pdf2md-gui; aktywny gdy jest PDF na liście.
        self.pdf2md_button.setVisible(self._pdf2md_gui_available())
        self.pdf2md_button.setEnabled(False)
        actions.addWidget(self.pdf2md_button)
        section.content_layout().addLayout(actions)

    def _build_engine_row(self) -> QWidget:
        """Buduje wiersz radiobuttonów wyboru silnika konwersji."""
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        self.engine_group = QButtonGroup(self)
        self._engine_radios: dict[str, QRadioButton] = {}
        radios = (
            ("auto", "Auto"),
            ("pandoc", "Pandoc"),
            ("calibre", "Calibre"),
            ("pdf2md", "pdf2md"),
        )
        for value, label in radios:
            radio = QRadioButton(label)
            radio.setToolTip(_engine_tooltip(value))
            radio.setProperty("engine", value)
            if value == "auto":
                radio.setChecked(True)
            # pdf2md działa tylko dla PDF — włączany dynamicznie po dodaniu PDF-a.
            if value == "pdf2md":
                radio.setEnabled(False)
            self.engine_group.addButton(radio)
            self._engine_radios[value] = radio
            row.addWidget(radio)
        row.addStretch(1)
        return widget

    def _pdf2md_available(self) -> bool:
        """Czy wykryto CLI ``pdf2md`` (silnik konwersji PDF)."""
        tool = self.tools.get("pdf2md")
        return tool is not None and tool.available

    def _pdf2md_gui_available(self) -> bool:
        """Czy wykryto ``pdf2md-gui`` (handoff „Otwórz w pdf2md")."""
        tool = self.tools.get("pdf2md_gui")
        return tool is not None and tool.available

    def _build_log(self, layout: QVBoxLayout) -> None:
        """Buduje pole logu konwersji."""
        section = Section(_("Log"))
        layout.addWidget(section, stretch=1)
        self.log_view = LogView()
        section.add_widget(self.log_view)

    # ── Logika ────────────────────────────────────────────────────────────────

    def _on_files_changed(self, files: list[Path]) -> None:
        """Podpowiada katalog wyjściowy i dostraja dostępność silników do plików."""
        if files and not self.output_entry.get().strip():
            self.output_entry.set(str(files[0].parent))
        self._apply_kindle_engine_lock(files)
        self._apply_pdf_engine_state(files)

    def _apply_kindle_engine_lock(self, files: list[Path]) -> None:
        """Dla plików Kindle wymusza silnik Calibre (Auto/Pandoc zablokowane)."""
        has_kindle = any(path.suffix.lower() in KINDLE_INPUT_EXTENSIONS for path in files)
        self.kindle_notice.setVisible(has_kindle)
        if has_kindle:
            self._engine_radios["calibre"].setChecked(True)
        self._engine_radios["auto"].setEnabled(not has_kindle)
        self._engine_radios["pandoc"].setEnabled(not has_kindle)

    def _apply_pdf_engine_state(self, files: list[Path]) -> None:
        """Włącza silnik i handoff pdf2md tylko, gdy na liście jest PDF i wykryto pdf2md."""
        has_pdf = any(path.suffix.lower() == ".pdf" for path in files)
        radio = self._engine_radios["pdf2md"]
        radio.setEnabled(has_pdf and self._pdf2md_available())
        if not radio.isEnabled() and radio.isChecked():
            self._engine_radios["auto"].setChecked(True)
        self.pdf2md_button.setVisible(self._pdf2md_gui_available())
        self.pdf2md_button.setEnabled(has_pdf and self._pdf2md_gui_available())

    def _confirm_file(self, path: Path) -> bool:
        """Odrzuca pliki Kindle z DRM (ostrzeżenie); PDF wymaga wyboru silnika."""
        suffix = path.suffix.lower()
        if suffix in KINDLE_INPUT_EXTENSIONS and has_kindle_drm(path):
            QMessageBox.warning(
                self,
                _("Plik z DRM"),
                _(
                    "Plik „{name}” jest zabezpieczony DRM — EpubForge nie konwertuje "
                    "plików DRM i nie usuwa zabezpieczeń."
                ).format(name=path.name),
            )
            return False
        if suffix != ".pdf":
            return True
        if self._pdf2md_available():
            return self._choose_pdf_engine()
        answer = QMessageBox.question(
            self,
            _("Konwersja PDF → EPUB"),
            _(
                "Konwersja PDF → EPUB jest eksperymentalna. Calibre wstawia sztywne "
                "marginesy i może łamać akapity. Najlepsze wyniki dla prostych PDF "
                "tekstowych. Kontynuować?"
            ),
        )
        return answer == QMessageBox.StandardButton.Yes

    def _choose_pdf_engine(self) -> bool:
        """Pyta o silnik PDF (pdf2md zalecany / Calibre eksperymentalny), zapamiętuje wybór."""
        box = QMessageBox(self)
        box.setWindowTitle(_("Konwersja PDF → EPUB"))
        box.setText(_("Wybierz silnik konwersji PDF → EPUB:"))
        box.setInformativeText(
            _(
                "pdf2md (zalecane) wydobywa czystszy tekst i osadza obrazy. "
                "Calibre jest eksperymentalny — sztywne marginesy i łamanie akapitów."
            )
        )
        pdf2md_button = box.addButton(_("pdf2md (zalecane)"), QMessageBox.ButtonRole.AcceptRole)
        calibre_button = box.addButton(
            _("Calibre (eksperymentalne)"), QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        remembered = self.config_data.get("pdf_engine")
        box.setDefaultButton(calibre_button if remembered == "calibre" else pdf2md_button)
        box.exec()

        clicked = box.clickedButton()
        if clicked not in (pdf2md_button, calibre_button):
            return False
        engine = "pdf2md" if clicked is pdf2md_button else "calibre"
        self.config_data["pdf_engine"] = engine
        self._engine_radios[engine].setChecked(True)
        return True

    def _first_pdf(self) -> Path | None:
        """Zwraca pierwszy plik PDF z listy wejściowej (lub ``None``)."""
        files: list[Path] = self.file_list.files()
        for path in files:
            if path.suffix.lower() == ".pdf":
                return path
        return None

    def _open_in_pdf2md(self) -> None:
        """Otwiera wybrany PDF w aplikacji pdf2md-gui (handoff)."""
        pdf = self._first_pdf()
        if pdf is None:
            self._set_status(_("Brak pliku PDF do otwarcia w pdf2md"))
            return
        try:
            launch_tool(self.tools.get("pdf2md_gui"), pdf)
        except ToolUnavailableError:
            self._set_status(_("Nie wykryto pdf2md"))
        except OSError as exc:
            self._set_status(_("Nie udało się uruchomić pdf2md: {error}").format(error=exc))
            QMessageBox.critical(
                self,
                _("pdf2md"),
                _("Nie udało się uruchomić programu:\n{error}").format(error=exc),
            )

    def _selected_engine(self) -> Engine:
        """Zwraca aktualnie wybrany silnik konwersji."""
        button = self.engine_group.checkedButton()
        return cast(Engine, button.property("engine")) if button is not None else "auto"

    def _build_convert_options(self) -> ConvertOptions:
        """Składa opcje konwersji z aktualnych wartości formularza."""
        author = self.author_edit.text().strip()
        metadata = Metadata(
            title=self.title_edit.text().strip(),
            creators=[author] if author else [],
            language=self.language_box.currentText().strip() or "en",
        )
        cover = self.cover_entry.get()
        return ConvertOptions(metadata=metadata, cover_image=Path(cover) if cover else None)

    def _convert(self) -> None:
        """Waliduje wejście i uruchamia konwersję w wątku roboczym."""
        if self._converting:
            return
        files = self.file_list.files()
        if not files:
            self._set_status(_("Brak plików do konwersji"))
            return
        output = self.output_entry.get().strip()

        self._converting = True
        self.convert_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.log_view.clear()
        self.progress_bar.setValue(0)
        self._set_status(_("Konwertowanie..."))

        remember_output_dir(self.config_data, output)
        options = self._build_convert_options()
        engine = self._selected_engine()
        output_dir = Path(output) if output else None

        self._worker = Worker(_run_conversion, files, output_dir, options, engine)
        self._worker.line.connect(self.log_view.append_line)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._finish_conversion)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.start()

    def _cancel(self) -> None:
        """Zgłasza anulowanie trwającej konwersji (kooperacyjne)."""
        if self._worker is not None and self._converting:
            self.cancel_button.setEnabled(False)
            self._set_status(_("Anulowanie…"))
            self._worker.cancel()

    def _on_progress(self, current: int, total: int) -> None:
        """Aktualizuje pasek postępu (procent silnika: current/total)."""
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)

    def _reset_after_run(self) -> None:
        """Przywraca stan przycisków po zakończeniu/przerwaniu pracy."""
        self._converting = False
        self.convert_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def _finish_conversion(self, result: object) -> None:
        """Aktualizuje UI po zakończeniu konwersji (wątek główny)."""
        succeeded, total = cast(tuple[int, int], result)
        self._reset_after_run()
        self.progress_bar.setValue(self.progress_bar.maximum())
        self._set_status(_("Zakończono: {done}/{total} OK").format(done=succeeded, total=total))

    def _on_cancelled(self) -> None:
        """Obsługuje anulowanie konwersji przez użytkownika."""
        self._reset_after_run()
        self.progress_bar.setValue(0)
        self.log_view.append_line(_("Anulowano"), "warn")
        self._set_status(_("Anulowano"))

    def _on_failed(self, message: str) -> None:
        """Obsługuje nieoczekiwany błąd wątku konwersji."""
        self._reset_after_run()
        self.log_view.append_line(_("BŁĄD: {message}").format(message=message), "err")
        self._set_status(_("Konwersja przerwana błędem"))

    def _set_status(self, text: str) -> None:
        """Ustawia tekst paska statusu zakładki."""
        self.status_label.setText(text)


def _run_conversion(
    emit_line: EmitLine,
    emit_progress: EmitProgress,
    should_cancel: ShouldCancel,
    files: list[Path],
    output_dir: Path | None,
    options: ConvertOptions,
    engine: Engine,
) -> tuple[int, int]:
    """Konwertuje pliki po kolei (wątek roboczy), streamuje log i postęp.

    Gdy ``output_dir`` jest ``None`` (puste pole), każdy plik trafia obok źródła.
    Zwraca krotkę ``(udane, łącznie)``; przerywa pętlę na żądanie ``should_cancel``.
    """
    succeeded = 0
    for source in files:
        if should_cancel():
            break
        target = resolve_output_dir(output_dir, source) / f"{source.stem}.epub"
        emit_line(f"→ {source.name} → {target.name}", "cmd")
        emit_progress(0, 100)
        try:
            result = to_epub_streaming(
                source,
                target,
                options,
                engine,
                on_line=emit_line,
                on_progress=emit_progress,
                should_cancel=should_cancel,
            )
        except (ConverterNotFoundError, ConversionError) as exc:
            emit_line(_("BŁĄD: {error}").format(error=exc), "err")
            continue
        if result.cancelled:
            break
        emit_line(_("OK [{engine}]: {name}").format(engine=result.engine, name=target.name), "ok")
        succeeded += 1
    return succeeded, len(files)


def _engine_tooltip(value: str) -> str:
    """Zwraca tooltip silnika konwersji jako literal gettext dla Babel."""
    if value == "pandoc":
        return _("Wymusza Pandoc (TXT/MD/DOCX/HTML/ODT/RTF)")
    if value == "calibre":
        return _("Wymusza Calibre ebook-convert (obsługuje też PDF/MOBI/FB2)")
    if value == "pdf2md":
        return _("Tylko PDF: pdf2md → Markdown → Pandoc EPUB (osadza obrazy)")
    return _("Auto: PDF → pdf2md (fallback Calibre), pozostałe → Pandoc (fallback Calibre)")


def _detect_tools() -> dict[str, Tool]:
    """Wykrywa narzędzia używane przez zakładkę konwertera (silnik i handoff pdf2md)."""
    return {"pdf2md": Tools.pdf2md(), "pdf2md_gui": Tools.pdf2md_gui()}
