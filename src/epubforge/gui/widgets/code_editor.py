"""Edytor kodu: QPlainTextEdit + numery linii + pasek wyszukiwania + status.

Kolory wyłącznie z :class:`Theme`. Numery linii to kanoniczny wzorzec Qt
(``blockCountChanged`` + ``updateRequest`` + ``lineNumberAreaPaintEvent``).
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QShortcut,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from epubforge.gui.editor_files import PROFILE_CSS, PROFILE_XML, Profile
from epubforge.gui.theme import Theme, current_theme
from epubforge.gui.widgets.syntax_highlight import (
    CssHighlighter,
    XmlHighlighter,
    _ThemedHighlighter,
)
from epubforge.i18n import _


class _LineNumberArea(QWidget):
    """Pasek numerów linii — deleguje rysowanie i szerokość do edytora."""

    def __init__(self, editor: _PlainEditor) -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802 — Qt API
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 — Qt API
        self._editor.line_number_area_paint_event(event)


class _PlainEditor(QPlainTextEdit):
    """QPlainTextEdit z obszarem numerów linii (kanoniczny wzorzec Qt)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._line_area = _LineNumberArea(self)
        self._bg = QColor(current_theme().bg2)
        self._fg = QColor(current_theme().fg3)
        self.blockCountChanged.connect(lambda _count: self._update_width())
        self.updateRequest.connect(self._update_area)
        self._update_width()

    def set_theme(self, theme: Theme) -> None:
        """Aktualizuje kolory paska numerów linii."""
        self._bg = QColor(theme.bg2)
        self._fg = QColor(theme.fg3)
        self._line_area.update()

    def line_number_area_width(self) -> int:
        """Szerokość paska zależna od liczby cyfr największego numeru linii."""
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_width(self) -> None:
        """Ustawia margines viewportu na szerokość paska numerów."""
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_area(self, rect: QRect, dy: int) -> None:
        """Przewija/odświeża pasek numerów zgodnie z ``updateRequest``."""
        if dy != 0:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_width()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 — Qt API
        super().resizeEvent(event)
        contents = self.contentsRect()
        self._line_area.setGeometry(
            QRect(contents.left(), contents.top(), self.line_number_area_width(), contents.height())
        )

    def line_number_area_paint_event(self, event: QPaintEvent) -> None:
        """Rysuje numery linii dla widocznych bloków."""
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), self._bg)
        painter.setPen(self._fg)
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        width = self._line_area.width() - 6
        height = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(
                    0, top, width, height, Qt.AlignmentFlag.AlignRight, str(block_number + 1)
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1


class CodeEditor(QWidget):
    """Edytor tekstu z numeracją linii, wyszukiwarką i statusem wiersz:kolumna."""

    modified_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = current_theme()
        self._highlighter: _ThemedHighlighter | None = None
        self._matches: list[int] = []
        self._match_index = -1
        self._match_length = 0
        self._build_ui()
        self._wire_shortcuts()

    # ── Budowa UI ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.editor = _PlainEditor(self)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(10)
        self.editor.setFont(font)
        self.editor.cursorPositionChanged.connect(self._update_status)
        self.editor.document().modificationChanged.connect(self.modified_changed.emit)
        layout.addWidget(self.editor, stretch=1)

        layout.addWidget(self._build_search_bar())

        self.status_label = QLabel(_("Wiersz {line}, kolumna {col}").format(line=1, col=1))
        self.status_label.setContentsMargins(6, 2, 6, 2)
        layout.addWidget(self.status_label)

    def _build_search_bar(self) -> QWidget:
        self.search_bar = QWidget(self)
        row = QHBoxLayout(self.search_bar)
        row.setContentsMargins(6, 4, 6, 4)
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText(_("Szukaj…"))
        self.search_field.textChanged.connect(self._on_search_changed)
        self.search_field.returnPressed.connect(self.find_next)
        row.addWidget(self.search_field, stretch=1)
        self.search_count = QLabel("0/0")
        row.addWidget(self.search_count)
        self.prev_button = QPushButton(_("Poprzedni"))
        self.prev_button.clicked.connect(self.find_previous)
        row.addWidget(self.prev_button)
        self.next_button = QPushButton(_("Następny"))
        self.next_button.clicked.connect(self.find_next)
        row.addWidget(self.next_button)
        self.search_bar.setVisible(False)
        return self.search_bar

    def _wire_shortcuts(self) -> None:
        context = Qt.ShortcutContext.WidgetWithChildrenShortcut
        find = QShortcut(QKeySequence.StandardKey.Find, self)
        find.setContext(context)
        find.activated.connect(self.show_search)
        nxt = QShortcut(QKeySequence(Qt.Key.Key_F3), self)
        nxt.setContext(context)
        nxt.activated.connect(self.find_next)
        prv = QShortcut(QKeySequence("Shift+F3"), self)
        prv.setContext(context)
        prv.activated.connect(self.find_previous)
        hide = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        hide.setContext(context)
        hide.activated.connect(self.hide_search)

    # ── API publiczne ───────────────────────────────────────────────────────--

    def load(self, text: str, profile: Profile | None = None) -> None:
        """Wczytuje tekst i ustawia podświetlanie wg profilu (xml/css/None)."""
        self._set_highlighter(profile)
        self.editor.setPlainText(text)
        self.editor.document().setModified(False)
        self.editor.moveCursor(QTextCursor.MoveOperation.Start)
        self._clear_search()

    def get_text(self) -> str:
        """Zwraca aktualną treść edytora."""
        return self.editor.toPlainText()

    def goto_line(self, line: int) -> None:
        """Ustawia kursor na początku linii (1-based) i centruje widok."""
        block = self.editor.document().findBlockByNumber(max(0, line - 1))
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        self.editor.setTextCursor(cursor)
        self.editor.centerCursor()

    @property
    def read_only(self) -> bool:
        """Czy edytor jest tylko do odczytu."""
        return self.editor.isReadOnly()

    @read_only.setter
    def read_only(self, value: bool) -> None:
        self.editor.setReadOnly(value)

    def is_modified(self) -> bool:
        """Czy dokument ma niezapisane zmiany."""
        return self.editor.document().isModified()

    def set_theme(self, theme: Theme) -> None:
        """Aktualizuje kolory (numery linii, podświetlanie, trafienia)."""
        self._theme = theme
        self.editor.set_theme(theme)
        if self._highlighter is not None:
            self._highlighter.set_theme(theme)
        self._refresh_match_highlight()

    # ── Wyszukiwanie ────────────────────────────────────────────────────────--

    def show_search(self) -> None:
        """Pokazuje pasek wyszukiwania i przenosi do niego fokus."""
        self.search_bar.setVisible(True)
        self.search_field.selectAll()
        self.search_field.setFocus()

    def hide_search(self) -> None:
        """Ukrywa pasek wyszukiwania i czyści podświetlenie trafień."""
        self.search_bar.setVisible(False)
        self._clear_search()
        self.editor.setFocus()

    def find_next(self) -> None:
        """Przechodzi do następnego trafienia."""
        self._step_match(1)

    def find_previous(self) -> None:
        """Przechodzi do poprzedniego trafienia."""
        self._step_match(-1)

    def match_count(self) -> int:
        """Liczba trafień bieżącego wyszukiwania (do testów)."""
        return len(self._matches)

    def _on_search_changed(self, pattern: str) -> None:
        """Przelicza trafienia po zmianie frazy."""
        self._matches = _find_all(self.get_text(), pattern)
        self._match_length = len(pattern)
        self._match_index = 0 if self._matches else -1
        self._refresh_match_highlight()
        if self._matches:
            self._select_match()

    def _step_match(self, delta: int) -> None:
        """Przesuwa indeks trafienia cyklicznie i zaznacza je."""
        if not self._matches:
            return
        self._match_index = (self._match_index + delta) % len(self._matches)
        self._refresh_match_highlight()
        self._select_match()

    def _select_match(self) -> None:
        """Ustawia kursor na bieżącym trafieniu i centruje widok."""
        start = self._matches[self._match_index]
        cursor = self.editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(start + self._match_length, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.centerCursor()

    def _refresh_match_highlight(self) -> None:
        """Podświetla wszystkie trafienia (kolor selection z Theme) i odświeża licznik."""
        selections: list[QTextEdit.ExtraSelection] = []
        for start in self._matches:
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor(self._theme.selection_bg))
            selection.format.setForeground(QColor(self._theme.selection_fg))
            cursor = self.editor.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(start + self._match_length, QTextCursor.MoveMode.KeepAnchor)
            selection.cursor = cursor
            selections.append(selection)
        self.editor.setExtraSelections(selections)
        total = len(self._matches)
        current = self._match_index + 1 if total else 0
        self.search_count.setText(f"{current}/{total}")

    def _clear_search(self) -> None:
        """Czyści stan wyszukiwania i podświetlenia."""
        self._matches = []
        self._match_index = -1
        self._match_length = 0
        self.editor.setExtraSelections([])
        self.search_count.setText("0/0")

    # ── Wewnętrzne ────────────────────────────────────────────────────────────

    def _set_highlighter(self, profile: Profile | None) -> None:
        """Podłącza highlighter odpowiedni dla profilu (albo żaden)."""
        self._highlighter = None
        document = self.editor.document()
        if profile == PROFILE_XML:
            self._highlighter = XmlHighlighter(document, self._theme)
        elif profile == PROFILE_CSS:
            self._highlighter = CssHighlighter(document, self._theme)

    def _update_status(self) -> None:
        """Aktualizuje status wiersz:kolumna z pozycji kursora."""
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self.status_label.setText(_("Wiersz {line}, kolumna {col}").format(line=line, col=col))


def _find_all(text: str, pattern: str) -> list[int]:
    """Zwraca pozycje startowe wszystkich (nienakładających się) wystąpień frazy.

    Wyszukiwanie bez rozróżniania wielkości liter; pusta fraza → brak trafień.
    """
    if not pattern:
        return []
    haystack = text.lower()
    needle = pattern.lower()
    positions: list[int] = []
    start = haystack.find(needle)
    while start != -1:
        positions.append(start)
        start = haystack.find(needle, start + len(needle))
    return positions
