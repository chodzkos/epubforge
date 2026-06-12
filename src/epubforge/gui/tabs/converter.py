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
    QPushButton,
    QRadioButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from epubforge.converters import SUPPORTED_INPUT_EXTENSIONS, ConvertOptions, to_epub
from epubforge.converters.to_epub import Engine
from epubforge.core import Metadata
from epubforge.core.config import Config
from epubforge.core.exceptions import ConversionError, ConverterNotFoundError
from epubforge.gui.output import remember_output_dir, remembered_output_dir, resolve_output_dir
from epubforge.gui.widgets import FileList, LogView, PathEntry, Section
from epubforge.gui.workers import EmitLine, EmitProgress, Worker
from epubforge.i18n import _

# Najczęstsze kody języków dla dropdownu (kolejność = priorytet wyświetlania).
_LANGUAGES = ["pl", "en", "de", "fr", "es", "it", "ru", "cs", "uk", "nl", "pt"]


class ConverterTab(QWidget):
    """Zakładka konwersji TXT/DOCX/HTML/MD/PDF… → EPUB."""

    def __init__(self, parent: QWidget | None = None, *, config: Config | None = None) -> None:
        super().__init__(parent)
        self.config_data: Config = config if config is not None else {}
        self._converting = False
        self._worker: Worker | None = None

        self._build_layout()

        remembered = remembered_output_dir(self.config_data)
        if remembered:
            self.output_entry.set(remembered)

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

        self.status_label = QLabel(_("Dodaj pliki wejściowe"))
        outer.addWidget(self.status_label)

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
        )
        self.cover_entry.entry.setToolTip(_("Opcjonalny obraz okładki (jpg/png/gif)"))
        form.addRow(_("Okładka"), self.cover_entry)

        form.addRow(_("Silnik"), self._build_engine_row())

        self.output_entry = PathEntry(
            mode="dir", config=self.config_data, remember_key="last_output_dir"
        )
        self.output_entry.entry.setToolTip(
            _("Folder na pliki .epub; puste = zapis obok pliku źródłowego")
        )
        form.addRow(_("Folder wyjściowy"), self.output_entry)

        self.convert_button = QPushButton(_("Konwertuj"))
        self.convert_button.setToolTip(
            _(
                "Konwertuje wybrane pliki do EPUB wybranym silnikiem.\n"
                "Puste pole 'Folder wyjściowy' = zapis obok pliku źródłowego."
            )
        )
        self.convert_button.clicked.connect(self._convert)
        section.content_layout().addWidget(self.convert_button)

    def _build_engine_row(self) -> QWidget:
        """Buduje wiersz radiobuttonów wyboru silnika konwersji."""
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        self.engine_group = QButtonGroup(self)
        for value, label in (("auto", "Auto"), ("pandoc", "Pandoc"), ("calibre", "Calibre")):
            radio = QRadioButton(label)
            radio.setToolTip(_engine_tooltip(value))
            radio.setProperty("engine", value)
            if value == "auto":
                radio.setChecked(True)
            self.engine_group.addButton(radio)
            row.addWidget(radio)
        row.addStretch(1)
        return widget

    def _build_log(self, layout: QVBoxLayout) -> None:
        """Buduje pole logu konwersji."""
        section = Section(_("Log"))
        layout.addWidget(section, stretch=1)
        self.log_view = LogView()
        section.add_widget(self.log_view)

    # ── Logika ────────────────────────────────────────────────────────────────

    def _on_files_changed(self, files: list[Path]) -> None:
        """Podpowiada katalog wyjściowy katalogiem pierwszego pliku, gdy pole puste."""
        if files and not self.output_entry.get().strip():
            self.output_entry.set(str(files[0].parent))

    def _confirm_file(self, path: Path) -> bool:
        """Dla plików PDF wymaga potwierdzenia (konwersja eksperymentalna)."""
        if path.suffix.lower() != ".pdf":
            return True
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
        self.log_view.clear()
        self._set_status(_("Konwertowanie..."))

        remember_output_dir(self.config_data, output)
        options = self._build_convert_options()
        engine = self._selected_engine()
        output_dir = Path(output) if output else None

        self._worker = Worker(_run_conversion, files, output_dir, options, engine)
        self._worker.line.connect(self.log_view.append_line)
        self._worker.done.connect(self._finish_conversion)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _finish_conversion(self, result: object) -> None:
        """Aktualizuje UI po zakończeniu konwersji (wątek główny)."""
        succeeded, total = cast(tuple[int, int], result)
        self._converting = False
        self.convert_button.setEnabled(True)
        self._set_status(_("Zakończono: {done}/{total} OK").format(done=succeeded, total=total))

    def _on_failed(self, message: str) -> None:
        """Obsługuje nieoczekiwany błąd wątku konwersji."""
        self._converting = False
        self.convert_button.setEnabled(True)
        self.log_view.append_line(_("BŁĄD: {message}").format(message=message), "err")
        self._set_status(_("Konwersja przerwana błędem"))

    def _set_status(self, text: str) -> None:
        """Ustawia tekst paska statusu zakładki."""
        self.status_label.setText(text)


def _run_conversion(
    emit_line: EmitLine,
    _emit_progress: EmitProgress,
    files: list[Path],
    output_dir: Path | None,
    options: ConvertOptions,
    engine: Engine,
) -> tuple[int, int]:
    """Konwertuje pliki po kolei (wątek roboczy) i streamuje log.

    Gdy ``output_dir`` jest ``None`` (puste pole), każdy plik trafia obok źródła.
    Zwraca krotkę ``(udane, łącznie)``.
    """
    succeeded = 0
    for source in files:
        target = resolve_output_dir(output_dir, source) / f"{source.stem}.epub"
        emit_line(f"→ {source.name} → {target.name}", "cmd")
        try:
            result = to_epub(source, target, options, engine)
        except (ConverterNotFoundError, ConversionError) as exc:
            emit_line(_("BŁĄD: {error}").format(error=exc), "err")
            continue
        if result.log:
            emit_line(result.log, "info")
        emit_line(_("OK [{engine}]: {name}").format(engine=result.engine, name=target.name), "ok")
        succeeded += 1
    return succeeded, len(files)


def _engine_tooltip(value: str) -> str:
    """Zwraca tooltip silnika konwersji jako literal gettext dla Babel."""
    if value == "pandoc":
        return _("Wymusza Pandoc (TXT/MD/DOCX/HTML/ODT/RTF)")
    if value == "calibre":
        return _("Wymusza Calibre ebook-convert (obsługuje też PDF/MOBI/FB2)")
    return _("Auto: PDF → Calibre, pozostałe → Pandoc (fallback Calibre)")
