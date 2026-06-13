"""Podświetlanie składni XML/CSS dla edytora EPUB.

Logika dopasowań tokenów żyje w czystych funkcjach (:func:`xml_spans`,
:func:`css_spans`) na zwykłym ``re`` — testowalnych bez Qt. Highlightery Qt
tylko mapują rodzaj tokenu na :class:`QTextCharFormat` w kolorach z :class:`Theme`
(jedyne źródło hexów) i obsługują wieloliniowe komentarze przez stan bloku.
"""

from __future__ import annotations

import re
from typing import ClassVar

from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat, QTextDocument

from epubforge.gui.theme import Theme, current_theme

# Span = (start, length, kind) — pozycja tokenu w jednej linii i jego rodzaj.
Span = tuple[int, int, str]

_XML_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"</?\s*[A-Za-z][\w:.-]*"), "tag"),
    (re.compile(r"/?>"), "tag"),
    (re.compile(r"[A-Za-z_:][\w:.-]*(?=\s*=)"), "attribute"),
    (re.compile(r"\"[^\"]*\"|'[^']*'"), "value"),
    (re.compile(r"&#?[\w]+;"), "entity"),
)

_CSS_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"@[\w-]+"), "atrule"),
    (re.compile(r"[^{}/;]+(?=\{)"), "selector"),
    (re.compile(r"[\w-]+(?=\s*:)"), "property"),
    (re.compile(r":\s*[^;{}]+"), "value"),
    (re.compile(r"!important\b"), "important"),
)

# Rodzaj tokenu → nazwa roli/stanu w Theme (kolory wyłącznie stąd).
_XML_COLORS = {
    "tag": "accent",
    "attribute": "amber",
    "value": "link",
    "entity": "red",
    "comment": "fg3",
}
_CSS_COLORS = {
    "atrule": "amber",
    "selector": "accent",
    "property": "link",
    "value": "fg2",
    "important": "red",
    "comment": "fg3",
}


def xml_spans(text: str) -> list[Span]:
    """Zwraca tokeny XML jednej linii (bez komentarzy — te liczy highlighter)."""
    return _spans(text, _XML_RULES)


def css_spans(text: str) -> list[Span]:
    """Zwraca tokeny CSS jednej linii (bez komentarzy — te liczy highlighter)."""
    return _spans(text, _CSS_RULES)


def _spans(text: str, rules: tuple[tuple[re.Pattern[str], str], ...]) -> list[Span]:
    """Stosuje reguły regex po kolei, zwracając listę spanów (start, długość, rodzaj)."""
    spans: list[Span] = []
    for pattern, kind in rules:
        for match in pattern.finditer(text):
            spans.append((match.start(), match.end() - match.start(), kind))
    return spans


class _ThemedHighlighter(QSyntaxHighlighter):
    """Wspólna baza: trzyma motyw, buduje formaty, obsługuje komentarze blokowe."""

    _COLORS: ClassVar[dict[str, str]] = {}
    _COMMENT_START = re.compile(r"")
    _COMMENT_END = re.compile(r"")

    def __init__(self, document: QTextDocument, theme: Theme | None = None) -> None:
        super().__init__(document)
        self._theme = theme if theme is not None else current_theme()
        self._formats = self._build_formats(self._theme)

    def set_theme(self, theme: Theme) -> None:
        """Aktualizuje kolory i ponownie podświetla dokument (sygnał zmiany motywu)."""
        self._theme = theme
        self._formats = self._build_formats(theme)
        self.rehighlight()

    def _build_formats(self, theme: Theme) -> dict[str, QTextCharFormat]:
        """Buduje formaty dla rodzajów tokenów (kolory z ról/stanów Theme)."""
        formats: dict[str, QTextCharFormat] = {}
        for kind, role in self._COLORS.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(getattr(theme, role)))
            if kind == "comment":
                fmt.setFontItalic(True)
            formats[kind] = fmt
        return formats

    def _spans(self, text: str) -> list[Span]:
        """Tokeny linii — nadpisywane w podklasie."""
        raise NotImplementedError

    def highlightBlock(self, text: str) -> None:  # noqa: N802 — Qt API
        """Koloruje linię: najpierw tokeny, potem nakładka komentarza (wygrywa)."""
        for start, length, kind in self._spans(text):
            fmt = self._formats.get(kind)
            if fmt is not None:
                self.setFormat(start, length, fmt)
        self._highlight_comments(text)

    def _highlight_comments(self, text: str) -> None:
        """Nakłada format komentarza, śledząc wieloliniowość przez stan bloku."""
        comment_fmt = self._formats["comment"]
        self.setCurrentBlockState(0)
        if self.previousBlockState() == 1:
            start = 0
        else:
            match = self._COMMENT_START.search(text)
            start = match.start() if match else -1
        while start >= 0:
            end_match = self._COMMENT_END.search(text, start)
            if end_match is None:
                self.setCurrentBlockState(1)
                self.setFormat(start, len(text) - start, comment_fmt)
                return
            finish = end_match.end()
            self.setFormat(start, finish - start, comment_fmt)
            next_match = self._COMMENT_START.search(text, finish)
            start = next_match.start() if next_match else -1


class XmlHighlighter(_ThemedHighlighter):
    """Podświetlanie XML/XHTML/OPF/NCX: tagi, atrybuty, wartości, encje, komentarze."""

    _COLORS = _XML_COLORS
    _COMMENT_START = re.compile(r"<!--")
    _COMMENT_END = re.compile(r"-->")

    def _spans(self, text: str) -> list[Span]:
        return xml_spans(text)


class CssHighlighter(_ThemedHighlighter):
    """Podświetlanie CSS: selektory, @-reguły, właściwości, wartości, !important."""

    _COLORS = _CSS_COLORS
    _COMMENT_START = re.compile(r"/\*")
    _COMMENT_END = re.compile(r"\*/")

    def _spans(self, text: str) -> list[Span]:
        return css_spans(text)
