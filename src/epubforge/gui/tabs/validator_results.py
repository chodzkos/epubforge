"""Model wierszy i prezentacja wyników zakładki Walidacja."""

from __future__ import annotations

import dataclasses
from collections import Counter
from pathlib import Path
from typing import Protocol

from chodzkos_gui_kit.palette import Palette as Theme
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QLabel, QTreeWidget, QTreeWidgetItem

from epubforge.i18n import _, ngettext
from epubforge.validators import AceMessage, Severity, ValidationMessage

_LOCATION_ROLE = Qt.ItemDataRole.UserRole


@dataclasses.dataclass(frozen=True)
class ResultRow:
    """Znormalizowany wiersz wspólny dla raportów EpubCheck i Ace."""

    severity: Severity
    code: str
    internal_path: str | None
    line: int | None
    message: str


def row_from_message(message: ValidationMessage) -> ResultRow:
    """Sprowadza komunikat EpubChecka do wspólnego wiersza."""
    return ResultRow(
        message.severity,
        message.code,
        message.internal_path,
        message.line,
        message.message,
    )


def row_from_ace(message: AceMessage) -> ResultRow:
    """Sprowadza naruszenie Ace do wspólnego wiersza."""
    return ResultRow(
        message.severity,
        message.rule,
        message.internal_path,
        None,
        message.message,
    )


class _EditorHandoff(Protocol):
    def open_in_editor(
        self, epub_path: Path, internal_path: str | None = None, line: int | None = None
    ) -> None: ...


class ValidatorResultsMixin:
    """Filtrowanie, drzewo i podsumowanie raportów walidacji."""

    tree: QTreeWidget
    show_errors: QCheckBox
    show_warnings: QCheckBox
    show_info: QCheckBox
    summary_label: QLabel
    _rows: list[ResultRow]
    _active_epub: Path | None
    _main_window: _EditorHandoff | None
    _theme: Theme

    def _populate_tree(self) -> None:
        """Wypełnia drzewo wierszami widocznymi według filtrów."""
        self.tree.clear()
        self.tree.addTopLevelItems(
            [self._make_item(row) for row in self._rows if self._severity_visible(row.severity)]
        )

    def _severity_visible(self, severity: Severity) -> bool:
        """Sprawdza, czy poziom komunikatu jest włączony w filtrach."""
        if severity in (Severity.FATAL, Severity.ERROR):
            return self.show_errors.isChecked()
        if severity == Severity.WARNING:
            return self.show_warnings.isChecked()
        return self.show_info.isChecked()

    def _make_item(self, row: ResultRow) -> QTreeWidgetItem:
        """Buduje wiersz drzewa, używając semantycznego koloru motywu."""
        where = row.internal_path or "—"
        if row.line is not None:
            where = f"{where}:{row.line}"
        item = QTreeWidgetItem([_severity_label(row.severity), row.code, where, row.message])
        color = QColor(_severity_color(row.severity, self._theme))
        for column in range(4):
            item.setForeground(column, color)
        item.setToolTip(3, row.message)
        item.setData(0, _LOCATION_ROLE, (row.internal_path, row.line))
        return item

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Otwiera komunikat z lokalizacją w wewnętrznym Edytorze."""
        location = item.data(0, _LOCATION_ROLE)
        if (
            not isinstance(location, tuple)
            or self._active_epub is None
            or self._main_window is None
        ):
            return
        internal_path, line = location
        if internal_path:
            self._main_window.open_in_editor(self._active_epub, internal_path, line)

    def _update_summary(self) -> None:
        """Aktualizuje podsumowanie raportu z poprawnymi formami mnogimi."""
        if self._active_epub is None:
            self.summary_label.setText("")
            return
        counts: Counter[Severity] = Counter(row.severity for row in self._rows)
        errors = counts[Severity.FATAL] + counts[Severity.ERROR]
        warnings = counts[Severity.WARNING]
        infos = counts[Severity.INFO]
        errors_text = ngettext("{n} błąd", "{n} błędów", errors).format(n=errors)
        warnings_text = ngettext("{n} ostrzeżenie", "{n} ostrzeżeń", warnings).format(n=warnings)
        infos_text = ngettext("{n} informacja", "{n} informacji", infos).format(n=infos)
        self.summary_label.setText(
            f"✗ {errors_text}  ·  ⚠ {warnings_text}  ·  ℹ {infos_text}"  # noqa: RUF001
        )

    def set_theme(self, theme: Theme) -> None:
        """Aktualizuje motyw i przemalowuje wiersze drzewa."""
        self._theme = theme
        self._populate_tree()


def _severity_label(severity: Severity) -> str:
    """Zwraca lokalizowaną etykietę poziomu."""
    return {
        Severity.FATAL: _("Krytyczny"),
        Severity.ERROR: _("Błąd"),
        Severity.WARNING: _("Ostrzeżenie"),
        Severity.INFO: _("Informacja"),
    }[severity]


def _severity_color(severity: Severity, theme: Theme) -> str:
    """Zwraca semantyczny kolor poziomu z palety gui-kit."""
    if severity in (Severity.FATAL, Severity.ERROR):
        return theme.red
    if severity == Severity.WARNING:
        return theme.amber
    return theme.fg2
