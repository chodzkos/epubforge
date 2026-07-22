"""Responsywny układ zakładki Edytor i przywracanie paneli domyślnych."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from chodzkos_gui_kit.qt.icons import get_icon
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from epubforge.core import Tool
from epubforge.gui.widgets.code_editor import CodeEditor
from epubforge.gui.widgets.css_inspector import CssInspector
from epubforge.gui.widgets.horizontal_strip import HorizontalStrip
from epubforge.gui.widgets.search_panel import SearchHost, SearchReplacePanel
from epubforge.i18n import _

_TREE_MIN_WIDTH = 180
_EDITOR_MIN_WIDTH = 300
_PREVIEW_MIN_WIDTH = 320
_INSPECTOR_MIN_WIDTH = 360
_SPLITTER_HANDLE_WIDTH = 8


class EditorLayoutMixin:
    """Buduje geometryczną część edytora bez logiki plików i renderowania."""

    code_editor: CodeEditor
    search_panel: SearchReplacePanel
    tree: QTreeWidget
    main_splitter: QSplitter
    content_splitter: QSplitter
    preview_split: QSplitter
    stack: QStackedWidget
    css_inspector: CssInspector
    book_preview: Any
    split_view_button: QToolButton
    code_view_button: QToolButton
    inspector_toggle: QToolButton
    _on_item_changed: Callable[..., None]
    _on_modified: Callable[..., None]
    _build_right_panel: Callable[[], QWidget]
    _choose_epub: Callable[..., None]
    _on_edit_toggled: Callable[..., None]
    _update_inspector: Callable[..., None]
    _save_epub: Callable[..., None]
    _current_is_html: Callable[[], bool]
    _launch_external_tool: Callable[[str], None]
    _tools: dict[str, Tool]
    _epub_path: Path | None

    def _build_ui(self) -> None:
        outer = QVBoxLayout(cast(QWidget, self))
        outer.setContentsMargins(12, 12, 12, 12)
        toolbar_host = QWidget()
        toolbar_layout = QVBoxLayout(toolbar_host)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.addWidget(self._build_toolbar())
        outer.addWidget(toolbar_host)

        self.info_bar = QLabel()
        self.info_bar.setWordWrap(True)
        self.info_bar.setVisible(False)
        outer.addWidget(self.info_bar)

        self.mode_label = QLabel()
        self.mode_label.setContentsMargins(2, 0, 2, 4)
        outer.addWidget(self.mode_label)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._configure_splitter(self.main_splitter)
        outer.addWidget(self.main_splitter, stretch=1)

        self.tree = QTreeWidget()
        self._configure_file_tree()
        self.tree.currentItemChanged.connect(self._on_item_changed)
        self.main_splitter.addWidget(self.tree)

        self.code_editor = self._new_code_editor()
        self.code_editor.modified_changed.connect(self._on_modified)
        self.main_splitter.addWidget(self._build_right_panel())
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 4)

        self.search_panel = self._new_search_panel()
        outer.addWidget(self.search_panel)
        QTimer.singleShot(0, self._restore_default_splitter_sizes)

    def _new_code_editor(self) -> CodeEditor:
        return CodeEditor()

    def _new_search_panel(self) -> SearchReplacePanel:
        return SearchReplacePanel(cast(SearchHost, self))

    def _build_toolbar(self) -> HorizontalStrip:
        strip = HorizontalStrip()
        toolbar = strip.row
        self.open_button = QPushButton(_("Otwórz EPUB…"))
        self.open_button.setToolTip(
            _("Otwórz plik EPUB do bezpiecznego podglądu i edycji jego zawartości")
        )
        self.open_button.clicked.connect(self._choose_epub)
        toolbar.addWidget(self.open_button)

        self.path_label = QLabel(_("Nie otwarto pliku"))
        self.path_label.setToolTip(_("Ścieżka aktualnie otwartego pliku EPUB"))
        self.path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(self.path_label, stretch=1)

        self.external_tool_buttons: dict[str, QPushButton] = {}
        for key, label in (("sigil", _("Sigil")), ("calibre_editor", _("Calibre Editor"))):
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, tool_key=key: self._launch_external_tool(tool_key)
            )
            toolbar.addWidget(button)
            self.external_tool_buttons[key] = button

        self.edit_toggle = QToolButton()
        self.edit_toggle.setToolTip(
            _("Włącz lub wyłącz edycję plików; startowo zawartość jest tylko do odczytu")
        )
        self.edit_toggle.setCheckable(True)
        self.edit_toggle.toggled.connect(self._on_edit_toggled)
        toolbar.addWidget(self.edit_toggle)

        self.inspector_toggle = QToolButton()
        self.inspector_toggle.setText(_("Inspektor CSS"))
        self.inspector_toggle.setToolTip(
            _("Pokaż lub ukryj analizę arkusza CSS albo kaskady elementu w dokładnym podglądzie")
        )
        self.inspector_toggle.setCheckable(True)
        self.inspector_toggle.setChecked(True)
        self.inspector_toggle.setEnabled(False)
        self.inspector_toggle.toggled.connect(lambda _checked: self._update_inspector())
        toolbar.addWidget(self.inspector_toggle)

        self.reset_layout_button = QToolButton()
        self.reset_layout_button.setText(_("Resetuj układ"))
        self.reset_layout_button.setIcon(get_icon("reset_colors"))
        self.reset_layout_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.reset_layout_button.setToolTip(
            _("Przywróć podstawowy układ paneli po dodatkowym potwierdzeniu")
        )
        self.reset_layout_button.clicked.connect(self._confirm_reset_layout)
        toolbar.addWidget(self.reset_layout_button)

        self.save_epub_button = QPushButton(_("Zapisz EPUB"))
        self.save_epub_button.setToolTip(
            _("Zapisz zmiany całej publikacji na dysku i utwórz kopię .bak")
        )
        self.save_epub_button.clicked.connect(self._save_epub)
        toolbar.addWidget(self.save_epub_button)
        strip.finish()
        return strip

    def _refresh_external_tool_actions(self) -> None:
        """Aktualizuje górny handoff do Sigila i edytora Calibre."""
        for key, button in self.external_tool_buttons.items():
            label = _("Sigil") if key == "sigil" else _("Calibre Editor")
            tool = self._tools.get(key)
            available = bool(tool and tool.available and tool.path)
            button.setEnabled(self._epub_path is not None and available)
            if not available:
                tooltip = _("Nie wykryto {tool}").format(tool=label)
            elif self._epub_path is None:
                tooltip = _("Najpierw otwórz EPUB")
            else:
                assert tool is not None and tool.path is not None
                tooltip = _(
                    "Otwórz cały aktualny EPUB w {tool}. Program zobaczy wersję zapisaną "
                    "na dysku, bez niezapisanych zmian Edytora. Wykryta ścieżka: {path}"
                ).format(tool=label, path=tool.path)
            button.setToolTip(tooltip)

    def _configure_file_tree(self) -> None:
        """Zapewnia natychmiastowy scroll i pełne, nieelidowane nazwy plików."""
        tree = self.tree
        tree.setHeaderHidden(True)
        tree.setMinimumWidth(_TREE_MIN_WIDTH)
        tree.setTextElideMode(Qt.TextElideMode.ElideNone)
        tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        header = tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

    @staticmethod
    def _configure_splitter(splitter: QSplitter) -> None:
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(_SPLITTER_HANDLE_WIDTH)
        splitter.setOpaqueResize(True)

    def _confirm_reset_layout(self) -> None:
        answer = QMessageBox.question(
            cast(QWidget, self),
            _("Reset układu edytora"),
            _(
                "Przywrócić podstawowy układ paneli? Zostaną zamknięte dodatkowe "
                "panele, ale treść EPUB-a i niezapisane zmiany pozostaną bez zmian."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._reset_editor_layout()

    def _reset_editor_layout(self) -> None:
        """Zamyka opcjonalne panele i odtwarza czytelne proporcje splitterów."""
        self.inspector_toggle.setChecked(False)
        self.split_view_button.setChecked(False)
        self.search_panel.setVisible(False)
        self.book_preview.reader_settings_button.setChecked(False)
        self.book_preview.diagnostics_button.setChecked(False)
        self.book_preview.compare_profiles_button.setChecked(False)
        if self._current_is_html():
            self.code_view_button.setChecked(True)
            self.stack.setCurrentIndex(0)
        self._restore_default_splitter_sizes()

    def _restore_default_splitter_sizes(self) -> None:
        """Przywraca proporcje drzewa, treści, podglądu i inspektora."""
        self._set_splitter_ratio(self.main_splitter, (1, 4))
        self._set_splitter_ratio(self.content_splitter, (3, 2))
        self._set_splitter_ratio(self.preview_split, (1, 1))

    @staticmethod
    def _set_splitter_ratio(splitter: QSplitter, ratio: tuple[int, ...]) -> None:
        total = max(splitter.width(), sum(ratio) * 100)
        unit = total / sum(ratio)
        splitter.setSizes([round(unit * part) for part in ratio])

    def _prepare_editor_panels(self, editor_side: QWidget) -> None:
        """Nadaje panelom minima, żeby zagnieżdżony splitter nie zwijał treści."""
        editor_side.setMinimumWidth(_EDITOR_MIN_WIDTH)
        self.stack.setMinimumWidth(_EDITOR_MIN_WIDTH)
        self.book_preview.setMinimumWidth(_PREVIEW_MIN_WIDTH)
        self.css_inspector.setMinimumWidth(_INSPECTOR_MIN_WIDTH)
        for splitter in (self.preview_split, self.content_splitter):
            self._configure_splitter(splitter)
