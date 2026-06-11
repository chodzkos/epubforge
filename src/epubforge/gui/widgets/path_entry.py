"""Pole ścieżki: ``QLineEdit`` + przycisk „…" otwierający ``QFileDialog``."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QToolButton,
    QWidget,
)

from epubforge.core.config import Config
from epubforge.gui.theme import native_file_dialogs

PathMode = Literal["dir", "file", "save"]
FileTypes = Sequence[tuple[str, str]]

_BROWSE_TOOLTIPS: dict[PathMode, str] = {
    "dir": "Wybierz folder",
    "file": "Wybierz plik",
    "save": "Wybierz miejsce i nazwę zapisu",
}

_DIALOG_TITLES: dict[PathMode, str] = {
    "dir": "Wybierz folder",
    "file": "Wybierz plik",
    "save": "Zapisz jako",
}


class PathEntry(QWidget):
    """Pole tekstowe z przyciskiem wyboru ścieżki (plik/folder/zapis).

    Emituje :attr:`path_changed` przy każdej zmianie tekstu. Jeśli przekazano
    ``config`` i ``remember_key``, zapamiętuje katalog ostatniego wyboru i używa
    go jako punktu startowego kolejnego dialogu.
    """

    path_changed = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        mode: PathMode = "dir",
        filetypes: FileTypes | None = None,
        placeholder: str = "",
        config: Config | None = None,
        remember_key: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode
        self.filetypes: FileTypes = filetypes or [("Wszystkie pliki", "*.*")]
        self._config = config
        self._remember_key = remember_key

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.entry = QLineEdit(self)
        if placeholder:
            self.entry.setPlaceholderText(placeholder)
        self.entry.textChanged.connect(self.path_changed.emit)
        layout.addWidget(self.entry, stretch=1)

        self.button = QToolButton(self)
        self.button.setText("…")
        self.button.setToolTip(_BROWSE_TOOLTIPS[mode])
        self.button.clicked.connect(self._browse)
        layout.addWidget(self.button)

    def get(self) -> str:
        """Zwraca aktualną ścieżkę bez białych znaków na końcach."""
        return self.entry.text().strip()

    def set(self, value: str) -> None:
        """Ustawia wartość pola."""
        self.entry.setText(value)

    def _browse(self) -> None:
        """Otwiera dialog wyboru ścieżki (natywny w trybie jasnym, Qt w ciemnym)."""
        options = QFileDialog.Option(0)
        if not native_file_dialogs():
            options = QFileDialog.Option.DontUseNativeDialog
        title = _DIALOG_TITLES[self.mode]
        start_dir = self._start_dir()
        if self.mode == "dir":
            path = QFileDialog.getExistingDirectory(self, title, start_dir, options=options)
        elif self.mode == "file":
            path, _ = QFileDialog.getOpenFileName(
                self, title, start_dir, self._filter(), options=options
            )
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, title, start_dir, self._filter(), options=options
            )
        if path:
            self.set(path)
            self._remember(path)

    def _filter(self) -> str:
        """Buduje string filtra Qt z listy ``(opis, wzorzec)``."""
        return ";;".join(f"{label} ({pattern})" for label, pattern in self.filetypes)

    def _start_dir(self) -> str:
        """Katalog startowy dialogu: bieżąca wartość, potem zapamiętany."""
        current = self.get()
        if current:
            path = Path(current)
            return str(path if path.is_dir() else path.parent)
        if self._config is not None and self._remember_key:
            return str(self._config.get(self._remember_key, ""))
        return ""

    def _remember(self, path: str) -> None:
        """Zapamiętuje katalog wybranej ścieżki w configu (jeśli skonfigurowano)."""
        if self._config is None or not self._remember_key:
            return
        chosen = Path(path)
        directory = chosen if chosen.is_dir() else chosen.parent
        self._config[self._remember_key] = str(directory)
