"""Lista plików z toolbarem i natywnym drag&drop (Qt)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from epubforge.core.config import Config
from epubforge.gui.file_dialogs import open_files, pick_dir

DEFAULT_EXTENSIONS = {".epub", ".txt", ".md", ".markdown", ".docx", ".html", ".htm", ".pdf"}


class FileList(QWidget):
    """Lista plików z przyciskami dodawania, usuwania i czyszczenia.

    Drag&drop jest natywny (Qt): upuszczenie plików dodaje pasujące rozszerzenia,
    a upuszczenie folderu skanuje go rekurencyjnie.

    Sygnały:
        files_changed: lista plików zmieniła się (niesie kopię listy).
        selection_changed: zmieniono zaznaczenie (niesie ``Path`` lub ``None``).
    """

    files_changed = Signal(list)
    selection_changed = Signal(object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        extensions: Iterable[str] | None = None,
        confirm: Callable[[Path], bool] | None = None,
        config: Config | None = None,
    ) -> None:
        super().__init__(parent)
        self.extensions = {ext.lower() for ext in (extensions or DEFAULT_EXTENSIONS)}
        # Hook wołany przed dodaniem pliku — zwrot False pomija plik
        # (np. potwierdzenie eksperymentalnej konwersji PDF).
        self.confirm = confirm
        # Config dla dopieszczonego dialogu Qt (pasek boczny, rozmiar okna).
        self._config = config
        self._files: list[Path] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self._add_files_btn = self._make_button("+ Pliki", "Dodaj pliki przez okno wyboru")
        self._add_files_btn.clicked.connect(self._add_files)
        self._add_folder_btn = self._make_button(
            "+ Folder", "Dodaj obsługiwane pliki z wybranego folderu"
        )
        self._add_folder_btn.clicked.connect(self._add_folder)
        self._remove_btn = self._make_button("Usuń", "Usuń zaznaczone pozycje z listy")
        self._remove_btn.clicked.connect(self._remove_selected)
        self._clear_btn = self._make_button("Wyczyść", "Usuń wszystkie pozycje z listy")
        self._clear_btn.clicked.connect(self.clear)
        toolbar.addWidget(self._add_files_btn)
        toolbar.addWidget(self._add_folder_btn)
        toolbar.addWidget(self._remove_btn)
        toolbar.addWidget(self._clear_btn)
        toolbar.addStretch(1)
        self.count_label = QLabel("0 plików")
        toolbar.addWidget(self.count_label)
        layout.addLayout(toolbar)

        self.listbox = QListWidget(self)
        self.listbox.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.listbox.setToolTip(
            "Lista plików — przeciągnij pliki tutaj lub użyj przycisków powyżej"
        )
        self.listbox.currentRowChanged.connect(self._on_current_row_changed)
        layout.addWidget(self.listbox, stretch=1)

        self.setAcceptDrops(True)

    # ── API publiczne ─────────────────────────────────────────────────────────

    def files(self) -> list[Path]:
        """Zwraca kopię listy plików."""
        return list(self._files)

    def add_files(self, paths: Iterable[Path]) -> None:
        """Dodaje pliki spełniające filtr rozszerzeń."""
        changed = False
        for path in paths:
            candidate = Path(path)
            if candidate.suffix.lower() not in self.extensions:
                continue
            if candidate in self._files:
                continue
            if self.confirm is not None and not self.confirm(candidate):
                continue
            self._files.append(candidate)
            changed = True
        if changed:
            self._refresh()

    def clear(self) -> None:
        """Czyści listę plików."""
        if not self._files:
            return
        self._files.clear()
        self._refresh()

    def current_path(self) -> Path | None:
        """Zwraca aktualnie zaznaczony plik (lub ``None``)."""
        row = self.listbox.currentRow()
        if 0 <= row < len(self._files):
            return self._files[row]
        return None

    def select_first(self) -> None:
        """Zaznacza pierwszy plik na liście, jeśli istnieje."""
        if self._files:
            self.listbox.setCurrentRow(0)

    # ── Drag & drop ─────────────────────────────────────────────────────────--

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 — Qt API
        """Akceptuje przeciąganie, gdy niesie URL-e plików/folderów."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 — Qt API
        """Dodaje upuszczone pliki; foldery skanuje rekurencyjnie."""
        paths: list[Path] = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if not local:
                continue
            path = Path(local)
            if path.is_dir():
                paths.extend(p for p in path.rglob("*") if p.is_file())
            else:
                paths.append(path)
        self.add_files(paths)
        event.acceptProposedAction()

    # ── Wewnętrzne ────────────────────────────────────────────────────────────

    def _make_button(self, text: str, tooltip: str) -> QPushButton:
        """Tworzy przycisk toolbaru z tooltipem."""
        button = QPushButton(text, self)
        button.setToolTip(tooltip)
        return button

    def _add_files(self) -> None:
        """Dodaje pliki wybrane w dialogu."""
        pattern = " ".join(f"*{ext}" for ext in sorted(self.extensions))
        paths = open_files(self, "Dodaj pliki", f"Obsługiwane ({pattern})", self._config)
        self.add_files(Path(path) for path in paths)

    def _add_folder(self) -> None:
        """Dodaje obsługiwane pliki z wybranego katalogu (bez rekursji)."""
        folder = pick_dir(self, "Dodaj folder", "", self._config)
        if not folder:
            return
        self.add_files(path for path in Path(folder).iterdir() if path.is_file())

    def _remove_selected(self) -> None:
        """Usuwa zaznaczone pozycje."""
        rows = sorted((index.row() for index in self.listbox.selectedIndexes()), reverse=True)
        if not rows:
            return
        for row in rows:
            self._files.pop(row)
        self._refresh()

    def _on_current_row_changed(self, _row: int) -> None:
        """Emituje sygnał zmiany zaznaczenia."""
        self.selection_changed.emit(self.current_path())

    def _refresh(self) -> None:
        """Odświeża widok listy i licznik."""
        self.listbox.clear()
        for path in self._files:
            QListWidgetItem(f"{path.name}  ({path.parent})", self.listbox)
        count = len(self._files)
        self.count_label.setText(f"{count} {_plural_files(count)}")
        self.files_changed.emit(self.files())


def _plural_files(count: int) -> str:
    """Zwraca polską odmianę słowa plik dla licznika."""
    if count == 1:
        return "plik"
    if 2 <= count <= 4:
        return "pliki"
    return "plików"
