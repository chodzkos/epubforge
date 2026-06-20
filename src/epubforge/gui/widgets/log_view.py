"""Widget logu: ``QPlainTextEdit`` tylko do odczytu z kolorowaniem poziomów."""

from __future__ import annotations

from chodzkos_gui_kit.palette import Palette as Theme
from chodzkos_gui_kit.qt.theme import current_palette as current_theme
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QWidget

# Maksymalna liczba bloków (linii) — chroni przed rozrostem przy długich logach.
_MAX_BLOCKS = 5000


class LogView(QPlainTextEdit):
    """Pole logu z dopisywaniem kolorowanych linii wg poziomu i ról motywu."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(_MAX_BLOCKS)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self._theme: Theme = current_theme()

    def set_theme(self, theme: Theme) -> None:
        """Aktualizuje motyw używany do kolorowania nowych linii."""
        self._theme = theme

    def append_line(self, text: str, level: str = "info") -> None:
        """Dopisuje pojedynczą linię logu w kolorze odpowiadającym poziomowi."""
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._color_for(level)))
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text.rstrip("\n") + "\n", fmt)
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.ensureCursorVisible()

    def _color_for(self, level: str) -> str:
        """Mapuje poziom linii na kolor z ról motywu (GUI_STANDARD §5)."""
        theme = self._theme
        # str(...) zawęża pole palety kitu (bez py.typed w v0.1.0 mypy widzi Any).
        return str(
            {
                "ok": theme.accent,
                "warn": theme.amber,
                "err": theme.red,
                "cmd": theme.fg3,
                "info": theme.fg2,
            }.get(level, theme.fg)
        )
