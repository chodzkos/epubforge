"""Prawy panel edytora EPUB: inspektor CSS + przybliżony podgląd HTML (F-D/F-P).

Wydzielone z :mod:`epubforge.gui.tabs.editor` jako mixin, żeby plik zakładki
trzymał się limitu rozmiaru. Mixin buduje prawą stronę (stos widoków + przełącznik
Kod/Podgląd + inspektor CSS) i obsługuje logikę podglądu; stan EPUB-a i edytora
dostarcza :class:`~epubforge.gui.tabs.editor.EditorTab`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from epubforge.core import Epub, Tool
from epubforge.gui import editor_files as ef
from epubforge.gui.external_tools import ToolUnavailableError, launch_tool
from epubforge.gui.theme import Theme
from epubforge.gui.widgets.code_editor import CodeEditor
from epubforge.gui.widgets.css_inspector import CssInspector
from epubforge.gui.widgets.html_preview import HtmlPreview
from epubforge.gui.widgets.image_preview import ImagePreview
from epubforge.i18n import _

# Strony QStackedWidget: edytor / podgląd obrazu / panel info / podgląd HTML.
_PAGE_EDITOR, _PAGE_IMAGE, _PAGE_INFO, _PAGE_HTML = 0, 1, 2, 3
# Opóźnienie odświeżania podglądu HTML przy edycji (ms).
_PREVIEW_DEBOUNCE_MS = 400


class EditorPreviewMixin:
    """Buduje i obsługuje prawy panel: inspektor CSS, podgląd HTML, przełącznik.

    Atrybuty (poniżej) ustawia :class:`EditorTab`; tu są tylko zadeklarowane dla
    statycznej analizy typów.
    """

    # Stan dostarczany przez EditorTab.
    _theme: Theme
    _tools: dict[str, Tool]
    _epub: Epub | None
    _epub_path: Path | None
    _current: str | None
    _media_types: dict[str, str]
    code_editor: CodeEditor
    _set_info_bar: Callable[[str], None]

    # Widgety tworzone w tym mixinie.
    stack: QStackedWidget
    image_preview: ImagePreview
    info_panel: QLabel
    html_preview: HtmlPreview
    css_inspector: CssInspector
    view_switch: QWidget
    view_group: QButtonGroup
    code_view_button: QToolButton
    preview_view_button: QToolButton

    # ── Budowa prawego panelu ─────────────────────────────────────────────────

    def _make_preview_timer(self) -> QTimer:
        """Tworzy jednostrzałowy timer debounce odświeżania podglądu HTML."""
        timer = QTimer(self)  # type: ignore[arg-type]  # EditorTab to QWidget
        timer.setSingleShot(True)
        timer.setInterval(_PREVIEW_DEBOUNCE_MS)
        timer.timeout.connect(self._render_html_preview)
        self._preview_timer = timer
        return timer

    def _build_right_panel(self) -> QWidget:
        """Buduje prawą stronę: stos widoków z przełącznikiem Kod/Podgląd + inspektor."""
        self.stack = QStackedWidget()
        self.image_preview = ImagePreview()
        self.info_panel = QLabel()
        self.info_panel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_panel.setWordWrap(True)
        self.html_preview = HtmlPreview(tools=self._tools, theme=self._theme)
        self.html_preview.open_external.connect(self._launch_external_tool)
        self.stack.addWidget(self.code_editor)
        self.stack.addWidget(self.image_preview)
        self.stack.addWidget(self.info_panel)
        self.stack.addWidget(self.html_preview)

        editor_side = QWidget()
        side_layout = QVBoxLayout(editor_side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.addWidget(self._build_view_switch())
        side_layout.addWidget(self.stack, stretch=1)

        right = QSplitter(Qt.Orientation.Horizontal)
        right.addWidget(editor_side)
        self.css_inspector = CssInspector(
            get_source=self.code_editor.get_text,
            apply_replacement=self._apply_css_replacement,
            theme=self._theme,
        )
        self.css_inspector.setVisible(False)
        right.addWidget(self.css_inspector)
        right.setStretchFactor(0, 3)
        right.setStretchFactor(1, 2)
        self.code_editor.editor.textChanged.connect(self._on_main_editor_changed)
        return right

    def _build_view_switch(self) -> QWidget:
        """Buduje przełącznik Kod/Podgląd (widoczny tylko dla plików HTML)."""
        self.view_switch = QWidget()
        row = QHBoxLayout(self.view_switch)
        row.setContentsMargins(0, 0, 0, 4)
        self.view_group = QButtonGroup(self)  # type: ignore[arg-type]
        self.view_group.setExclusive(True)
        self.code_view_button = QToolButton()
        self.code_view_button.setText(_("Kod"))
        self.code_view_button.setCheckable(True)
        self.code_view_button.setChecked(True)
        self.preview_view_button = QToolButton()
        self.preview_view_button.setText(_("Podgląd"))
        self.preview_view_button.setCheckable(True)
        self.preview_view_button.setToolTip(_("Przybliżony podgląd HTML (silnik Qt)"))
        self.view_group.addButton(self.code_view_button)
        self.view_group.addButton(self.preview_view_button)
        self.preview_view_button.toggled.connect(self._on_preview_toggled)
        row.addWidget(self.code_view_button)
        row.addWidget(self.preview_view_button)
        row.addStretch(1)
        self.view_switch.setVisible(False)
        return self.view_switch

    # ── Inspektor CSS ─────────────────────────────────────────────────────────

    def _current_is_css(self) -> bool:
        """Czy bieżący plik jest arkuszem CSS pokazanym w edytorze."""
        return (
            self._current is not None
            and self.stack.currentIndex() == _PAGE_EDITOR
            and ef.profile_for(self._current, self._media_types.get(self._current))
            == ef.PROFILE_CSS
        )

    def _update_inspector(self) -> None:
        """Pokazuje inspektor tylko dla CSS i gdy toggle włączony; odświeża go."""
        is_css = self._current_is_css()
        self.inspector_toggle.setEnabled(is_css)  # type: ignore[attr-defined]
        visible = is_css and self.inspector_toggle.isChecked()  # type: ignore[attr-defined]
        self.css_inspector.setVisible(visible)
        if visible:
            self.css_inspector.refresh()

    def _on_main_editor_changed(self) -> None:
        """Edycja → odroczone odświeżenie inspektora CSS i podglądu HTML (gdy aktywne)."""
        if self.css_inspector.isVisible():
            self.css_inspector.schedule_external_refresh()
        if self._preview_active():
            self._preview_timer.start()

    def _apply_css_replacement(self, start: int, end: int, new_text: str) -> None:
        """Wpisuje zmianę reguły do edytora JEDNĄ operacją kursora (undo cofa całość)."""
        editor = self.code_editor.editor
        cursor = editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(new_text)
        editor.setTextCursor(cursor)

    # ── Podgląd HTML ──────────────────────────────────────────────────────────

    def _current_is_html(self) -> bool:
        """Czy bieżący plik to dokument (X)HTML pokazany w edytorze."""
        return self._current is not None and ef.is_html(
            self._current, self._media_types.get(self._current)
        )

    def _preview_active(self) -> bool:
        """Czy podgląd HTML jest aktualnie pokazany."""
        return self.stack.currentIndex() == _PAGE_HTML

    def _update_view_switch(self, internal: str, media_type: str | None) -> None:
        """Pokazuje przełącznik Kod/Podgląd tylko dla HTML i resetuje go do Kodu."""
        is_html = ef.is_html(internal, media_type)
        self.view_switch.setVisible(is_html)
        if is_html and not self.code_view_button.isChecked():
            self.code_view_button.setChecked(True)  # reset do Kodu przy zmianie pliku

    def _on_preview_toggled(self, active: bool) -> None:
        """Przełącza prawy panel między kodem a podglądem HTML."""
        if active:
            self._render_html_preview()
            self.stack.setCurrentIndex(_PAGE_HTML)
        elif self.stack.currentIndex() == _PAGE_HTML:
            self.stack.setCurrentIndex(_PAGE_EDITOR)

    def _render_html_preview(self) -> None:
        """Renderuje bieżącą treść edytora w podglądzie HTML (z osadzeniem obrazków)."""
        if self._current is None or self._epub is None:
            return
        self.html_preview.set_content(self.code_editor.get_text(), self._epub, self._current)

    def _launch_external_tool(self, key: str) -> None:
        """Otwiera bieżący EPUB w narzędziu zewnętrznym (Sigil/Calibre Editor)."""
        label = {"sigil": "Sigil", "calibre_editor": "Calibre Editor"}.get(key, key)
        if self._epub_path is None:
            self._set_info_bar(_("Najpierw otwórz EPUB"))
            return
        try:
            launch_tool(self._tools.get(key), self._epub_path)
        except ToolUnavailableError:
            self._set_info_bar(_("Nie wykryto {tool}").format(tool=label))
        except OSError as exc:
            self._set_info_bar(
                _("Nie udało się uruchomić {tool}: {error}").format(tool=label, error=exc)
            )
