"""Zakładka edycji metadanych Dublin Core (Qt)."""

from __future__ import annotations

from collections.abc import Callable
from math import isfinite
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from epubforge.core import Epub, EpubError, Metadata, Tool, Tools
from epubforge.gui.external_tools import ToolUnavailableError, launch_tool
from epubforge.gui.widgets import (
    FileList,
    PathEntry,
    Section,
    file_list_count_label,
    file_list_texts,
    make_scrollable,
    path_entry_texts,
)
from epubforge.i18n import _, ngettext

_TOOL_LABELS = {
    "sigil": "Sigil",
    "calibre_editor": "Calibre Editor",
    "calibre_viewer": "Calibre Viewer",
}


class MetadataTab(QWidget):
    """Zakładka do przeglądania i edycji metadanych EPUB."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tools: dict[str, Tool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.tools = tools if tools is not None else _detect_tools()
        self.current_path: Path | None = None
        self._loaded_metadata: Metadata | None = None
        self.tool_buttons: dict[str, QPushButton] = {}

        self._build_layout()
        self._refresh_tool_buttons()

    def _build_layout(self) -> None:
        """Buduje dwukolumnowy układ zakładki."""
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, stretch=1)

        left = QWidget()
        self._build_file_browser(left)
        right = QWidget()
        self._build_form(right)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        self.status_label = QLabel(_("Wybierz plik EPUB"))
        outer.addWidget(self.status_label)
        outer.addStretch(1)

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(make_scrollable(content))
        self.setLayout(root)

    def _build_file_browser(self, parent: QWidget) -> None:
        """Buduje panel wyboru folderu i listy EPUB."""
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 10, 0)
        browser = Section(_("Pliki EPUB"))
        layout.addWidget(browser)

        self.folder_entry = PathEntry(
            mode="dir", placeholder=_("Folder z plikami EPUB"), texts=path_entry_texts()
        )
        self.folder_entry.entry.setToolTip(_("Folder z plikami EPUB do edycji metadanych"))
        self.folder_entry.path_changed.connect(self._load_folder)
        browser.add_widget(self.folder_entry)

        self.file_list = FileList(
            extensions={".epub"},
            texts=file_list_texts(),
            count_label=file_list_count_label,
        )
        self.file_list.files_changed.connect(self._on_files_changed)
        self.file_list.selection_changed.connect(self._on_file_selected)
        browser.add_widget(self.file_list)

    def _build_form(self, parent: QWidget) -> None:
        """Buduje formularz metadanych i przyciski akcji."""
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        form_section = Section(_("Metadane Dublin Core"))
        layout.addWidget(form_section, stretch=1)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_section.content_layout().addLayout(form)

        self.title_edit = self._line_edit(_("Tytuł książki (dc:title)"))
        form.addRow(_("Tytuł"), self.title_edit)
        form.addRow(_("Cykl"), self._build_series_row())
        self.creators_edit = self._text_edit(
            _("Autorzy — jeden na linię; format: Nazwisko, Imię"), height=3
        )
        form.addRow(_("Autorzy"), self.creators_edit)
        self.language_edit = self._line_edit(_("Kod języka, np. pl, en (dc:language)"))
        self.language_edit.setText("en")
        form.addRow(_("Język"), self.language_edit)
        self.publisher_edit = self._line_edit(_("Wydawca (dc:publisher)"))
        form.addRow(_("Wydawca"), self.publisher_edit)
        self.date_edit = self._line_edit(_("Data publikacji w formacie ISO: RRRR-MM-DD"))
        form.addRow(_("Data"), self.date_edit)
        self.identifier_edit = self._line_edit(_("Identyfikator: ISBN lub UUID (dc:identifier)"))
        form.addRow("ISBN", self.identifier_edit)
        self.subjects_edit = self._text_edit(
            _("Tematy/tagi — jeden na linię (dc:subject)"), height=3
        )
        form.addRow(_("Tematy"), self.subjects_edit)
        self.description_edit = self._text_edit(
            _("Opis/streszczenie książki (dc:description)"), height=7
        )
        form.addRow(_("Opis"), self.description_edit)

        form_section.content_layout().addLayout(self._build_actions())

    def _build_series_row(self) -> QWidget:
        """Buduje wiersz z nazwą cyklu i numerem tomu."""
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        self.series_edit = self._line_edit(_("Nazwa cyklu/serii, np. Wiedźmin"))
        row.addWidget(self.series_edit, stretch=1)
        label = QLabel(_("Tom nr:"))
        row.addWidget(label)
        self.series_index_edit = QLineEdit()
        self.series_index_edit.setToolTip(_("Numer tomu w cyklu, np. 2 (można 1.5)"))
        self.series_index_edit.setMaximumWidth(80)
        row.addWidget(self.series_index_edit)
        return widget

    def _build_actions(self) -> QHBoxLayout:
        """Buduje pasek akcji: Zapisz po lewej, narzędzia po prawej."""
        actions = QHBoxLayout()
        save = QPushButton(_("Zapisz"))
        save.setToolTip(_("Zapisuje metadane do wybranego EPUB"))
        save.clicked.connect(self._save_metadata)
        actions.addWidget(save)
        actions.addStretch(1)
        for key, label in _TOOL_LABELS.items():
            button = QPushButton(label)
            button.clicked.connect(_make_external_callback(self, key, label))
            actions.addWidget(button)
            self.tool_buttons[key] = button
        return actions

    def _line_edit(self, tooltip: str) -> QLineEdit:
        """Tworzy jednolinijkowe pole z tooltipem."""
        edit = QLineEdit()
        edit.setToolTip(tooltip)
        return edit

    def _text_edit(self, tooltip: str, *, height: int) -> QPlainTextEdit:
        """Tworzy wielowierszowe pole o przybliżonej wysokości w liniach."""
        edit = QPlainTextEdit()
        edit.setToolTip(tooltip)
        edit.setTabChangesFocus(True)
        line_height = edit.fontMetrics().lineSpacing()
        edit.setMinimumHeight(line_height * height + 12)
        return edit

    # ── Logika ────────────────────────────────────────────────────────────────

    def _load_folder(self, raw_path: str) -> None:
        """Wczytuje EPUB-y z podanego folderu do listy plików."""
        if not raw_path:
            return
        path = Path(raw_path).expanduser()
        if not path.is_dir():
            self._set_status(_("Wybrany folder nie istnieje"))
            return
        self.current_path = None
        self._clear_form()
        self.file_list.clear()
        self.file_list.add_files(sorted(path.glob("*.epub")))
        count = len(self.file_list.files())
        self._set_status(
            ngettext("Wczytano {n} plik EPUB", "Wczytano {n} plików EPUB", count).format(n=count)
        )

    def _on_files_changed(self, files: list[Path]) -> None:
        """Czyści wybór lub automatycznie ładuje pierwszy plik z listy."""
        if self.current_path in files:
            return
        self.current_path = None
        self._clear_form()
        if files:
            self.file_list.select_first()

    def _on_file_selected(self, path: Path | None) -> None:
        """Ładuje metadane zaznaczonego pliku."""
        if path is not None:
            self._load_metadata(path)

    def _load_metadata(self, path: Path) -> None:
        """Czyta metadane z EPUB i wypełnia formularz."""
        try:
            with Epub(path) as epub:
                metadata = epub.metadata
        except (EpubError, OSError, KeyError) as exc:
            self._set_status(_("Nie udało się wczytać metadanych: {error}").format(error=exc))
            QMessageBox.critical(
                self,
                _("Metadane"),
                _("Nie udało się wczytać metadanych:\n{error}").format(error=exc),
            )
            return
        self.current_path = path
        self._loaded_metadata = metadata
        self._set_form(metadata)
        self._set_status(_("Wczytano metadane: {name}").format(name=path.name))

    def _save_metadata(self) -> None:
        """Zapisuje metadane do aktualnego EPUB przez setter Epub.metadata."""
        if self.current_path is None:
            self._set_status(_("Wybierz plik EPUB przed zapisem"))
            return
        metadata = self._metadata_from_form()
        try:
            with Epub(self.current_path) as epub:
                epub.metadata = metadata
        except (EpubError, OSError, KeyError) as exc:
            self._set_status(_("Nie udało się zapisać metadanych: {error}").format(error=exc))
            QMessageBox.critical(
                self,
                _("Metadane"),
                _("Nie udało się zapisać metadanych:\n{error}").format(error=exc),
            )
            return
        self._loaded_metadata = metadata
        self._set_status(_("Zapisano metadane: {name}").format(name=self.current_path.name))

    def _open_external(self, key: str, label: str) -> None:
        """Uruchamia zewnętrzny edytor/podgląd dla aktualnego EPUB."""
        if self.current_path is None:
            self._set_status(_("Wybierz plik EPUB"))
            return
        try:
            launch_tool(self.tools.get(key), self.current_path)
        except ToolUnavailableError:
            self._set_status(_("Nie wykryto {tool}").format(tool=label))
        except OSError as exc:
            self._set_status(
                _("Nie udało się uruchomić {tool}: {error}").format(tool=label, error=exc)
            )
            QMessageBox.critical(
                self,
                label,
                _("Nie udało się uruchomić programu:\n{error}").format(error=exc),
            )

    def _refresh_tool_buttons(self) -> None:
        """Aktualizuje stan przycisków narzędzi zewnętrznych."""
        for key, label in _TOOL_LABELS.items():
            button = self.tool_buttons[key]
            tool = self.tools.get(key)
            if tool is not None and tool.available and tool.path is not None:
                button.setEnabled(True)
                button.setToolTip(str(tool.path))
            else:
                button.setEnabled(False)
                button.setToolTip(_("Nie wykryto {tool}").format(tool=label))

    def _set_form(self, metadata: Metadata) -> None:
        """Przepisuje obiekt Metadata do pól formularza."""
        self.title_edit.setText(metadata.title)
        self.series_edit.setText(metadata.series)
        self.series_index_edit.setText(_format_series_index(metadata.series_index))
        self.language_edit.setText(metadata.language)
        self.publisher_edit.setText(metadata.publisher)
        self.date_edit.setText(metadata.date)
        self.identifier_edit.setText(metadata.identifier)
        self.creators_edit.setPlainText("\n".join(metadata.creators))
        self.subjects_edit.setPlainText("\n".join(metadata.subjects))
        self.description_edit.setPlainText(metadata.description)

    def _metadata_from_form(self) -> Metadata:
        """Buduje Metadata z aktualnych wartości formularza."""
        return Metadata(
            title=self.title_edit.text().strip(),
            creators=_split_lines(self.creators_edit.toPlainText()),
            language=self.language_edit.text().strip() or "en",
            identifier=self.identifier_edit.text().strip(),
            publisher=self.publisher_edit.text().strip(),
            date=self.date_edit.text().strip(),
            description=self.description_edit.toPlainText().strip(),
            subjects=_split_lines(self.subjects_edit.toPlainText()),
            series=self.series_edit.text().strip(),
            series_index=self._series_index_from_form(),
        )

    def _clear_form(self) -> None:
        """Czyści formularz metadanych."""
        self._loaded_metadata = None
        self._set_form(Metadata())

    def _series_index_from_form(self) -> float | None:
        """Parsuje numer tomu, łagodnie ignorując niepoprawną wartość."""
        raw_value = self.series_index_edit.text().strip()
        if not raw_value:
            return None
        try:
            value = float(raw_value)
        except ValueError:
            return self._warn_invalid_series_index()
        if not isfinite(value):
            return self._warn_invalid_series_index()
        return value

    def _warn_invalid_series_index(self) -> float | None:
        """Pokazuje ostrzeżenie i zachowuje poprzedni numer tomu."""
        previous = self._loaded_metadata.series_index if self._loaded_metadata is not None else None
        self._set_status(_("Tom nr nie jest liczbą; zapisano pozostałe metadane"))
        QMessageBox.warning(
            self,
            _("Metadane"),
            _("Pole „Tom nr” musi być liczbą, np. 2 albo 1.5. Ta wartość nie zostanie zmieniona."),
        )
        return previous

    def _set_status(self, text: str) -> None:
        """Ustawia tekst paska statusu zakładki."""
        self.status_label.setText(text)


def _detect_tools() -> dict[str, Tool]:
    """Wykrywa narzędzia używane przez zakładkę metadanych."""
    return {
        "sigil": Tools.sigil(),
        "calibre_editor": Tools.calibre_editor(),
        "calibre_viewer": Tools.calibre_viewer(),
    }


def _make_external_callback(tab: MetadataTab, key: str, label: str) -> Callable[[], None]:
    """Tworzy callback bez późnego wiązania zmiennych pętli."""

    def callback() -> None:
        tab._open_external(key, label)

    return callback


def _format_series_index(value: float | None) -> str:
    """Formatuje numer tomu do pola formularza."""
    if value is None:
        return ""
    return str(int(value)) if value.is_integer() else str(value)


def _split_lines(value: str) -> list[str]:
    """Rozbija wielowierszową wartość formularza na niepuste wpisy."""
    return [line.strip() for line in value.splitlines() if line.strip()]
