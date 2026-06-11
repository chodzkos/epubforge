"""Sekcja UI oparta o ``QGroupBox`` z tytułem i wewnętrznym marginesem."""

from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QWidget


class Section(QGroupBox):
    """Opakowanie dla grupy powiązanych kontrolek (ramka z tytułem).

    Tworzy wewnętrzny ``QVBoxLayout`` z marginesem zgodnym z GUI_STANDARD §5
    (10-12 px). Treść dokładamy metodą :meth:`add_widget` lub przez
    :meth:`content_layout`.
    """

    def __init__(self, title: str, parent: QWidget | None = None, padding: int = 12) -> None:
        super().__init__(title, parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(padding, padding, padding, padding)
        self._layout.setSpacing(8)

    def content_layout(self) -> QVBoxLayout:
        """Zwraca wewnętrzny layout sekcji do ręcznego dokładania kontrolek."""
        return self._layout

    def add_widget(self, widget: QWidget) -> None:
        """Dodaje widget do sekcji."""
        self._layout.addWidget(widget)
