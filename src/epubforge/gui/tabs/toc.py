"""Zakładka „Spis treści" — podgląd, generowanie, naprawa i edycja drzewa TOC.

Model (``list[TocEntry]``) jest źródłem prawdy; widok jest z niego przebudowywany.
Drag&drop działa w trybie ``InternalMove``, ale przeniesienie liczy się na modelu
(``move_entry``) i dopiero potem odświeża widok — dzięki temu logika jest
testowalna bez symulacji zdarzeń Qt.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from chodzkos_gui_kit.palette import Palette as Theme
from chodzkos_gui_kit.qt.theme import current_palette as current_theme
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from epubforge.core import ConfigStore, Epub, ResourceLimitError
from epubforge.gui.widgets import PathEntry, make_scrollable, path_entry_texts
from epubforge.i18n import _, ngettext
from epubforge.toc import (
    MoveMode,
    TocEntry,
    TocProblem,
    generate_toc,
    move_entry,
    parent_of,
    read_toc,
    repair_toc,
    siblings_of,
    validate_toc,
    write_toc,
)
from epubforge.toc.limits import validate_toc_structure

_TITLE_COL = 0
_TARGET_COL = 1
_ENTRY_ROLE = Qt.ItemDataRole.UserRole

_DROP_MODES: dict[QAbstractItemView.DropIndicatorPosition, MoveMode] = {
    QAbstractItemView.DropIndicatorPosition.OnItem: "into",
    QAbstractItemView.DropIndicatorPosition.AboveItem: "before",
    QAbstractItemView.DropIndicatorPosition.BelowItem: "after",
}


class _TocTree(QTreeWidget):
    """Drzewo TOC z natywnym D&D, które zgłasza żądanie przeniesienia sygnałem.

    Domyślne przenoszenie Qt jest pomijane (``event.ignore``) — model jest
    źródłem prawdy, więc tab sam woła ``move_entry`` i przebudowuje widok.
    """

    move_requested = Signal(object, object, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHeaderLabels([_("Tytuł"), _("Cel")])
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 — Qt API
        """Wyznacza (źródło, cel, tryb) i deleguje do modelu zamiast ruszać widok."""
        source = self.currentItem()
        target = self.itemAt(event.position().toPoint())
        mode = _DROP_MODES.get(self.dropIndicatorPosition())
        if source is not None and target is not None and mode is not None and source is not target:
            self.move_requested.emit(source, target, mode)
        event.ignore()


class TocTab(QWidget):
    """Edytor spisu treści EPUB: drzewo z D&D, generowanie i naprawa."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        config: ConfigStore | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._theme: Theme = current_theme()
        self._epub: Epub | None = None
        self._epub_path: Path | None = None
        self._entries: list[TocEntry] = []
        self._items: dict[int, TocEntry] = {}
        self._dirty = False

        self._build_ui()
        self._refresh_actions()

    # ── Budowa UI ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(12, 12, 12, 12)

        self.path_entry = PathEntry(
            mode="file",
            filetypes=[(_("Pliki EPUB"), "*.epub")],
            placeholder=_("Wskaż plik EPUB…"),
            config=self._config,
            remember_key="toc_last_dir",
            texts=path_entry_texts(),
        )
        self.path_entry.path_changed.connect(self._on_path_changed)
        outer.addWidget(self.path_entry)

        outer.addLayout(self._build_toolbar())

        self.tree = _TocTree()
        self.tree.move_requested.connect(self._on_move_requested)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        outer.addWidget(self.tree, stretch=1)

        self.status_label = QLabel(_("Wskaż plik EPUB, aby wczytać spis treści."))
        outer.addWidget(self.status_label)
        outer.addStretch(1)

        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(make_scrollable(content))
        self.setLayout(root)

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self.generate_button = self._button(
            _("Generuj"), _("Zbuduj spis z nagłówków"), self._generate
        )
        bar.addWidget(self.generate_button)
        bar.addWidget(QLabel(_("Poziom:")))
        self.level_spin = QSpinBox()
        self.level_spin.setRange(1, 6)
        self.level_spin.setValue(3)
        self.level_spin.setToolTip(_("Najgłębszy poziom nagłówka przy generowaniu"))
        bar.addWidget(self.level_spin)
        self.repair_button = self._button(_("Napraw"), _("Usuń martwe wpisy"), self._repair)
        bar.addWidget(self.repair_button)
        bar.addSpacing(12)
        self.add_button = self._button(_("Dodaj"), _("Dodaj nową pozycję"), self._add_entry)
        bar.addWidget(self.add_button)
        self.remove_button = self._button(
            _("Usuń"), _("Usuń zaznaczoną pozycję"), self._remove_entry
        )
        bar.addWidget(self.remove_button)
        self.up_button = self._button("⬆", _("W górę (rodzeństwo)"), lambda: self._reorder("up"))
        bar.addWidget(self.up_button)
        self.down_button = self._button("⬇", _("W dół (rodzeństwo)"), lambda: self._reorder("down"))
        bar.addWidget(self.down_button)
        self.outdent_button = self._button("⬅", _("Wyżej (poziom)"), lambda: self._reorder("out"))
        bar.addWidget(self.outdent_button)
        self.indent_button = self._button("➡", _("Głębiej (poziom)"), lambda: self._reorder("in"))
        bar.addWidget(self.indent_button)
        bar.addStretch(1)
        self.save_button = self._button(
            _("Zapisz do EPUB"), _("Zapisz spis treści (nav + ncx) do pliku"), self._save
        )
        bar.addWidget(self.save_button)
        return bar

    def _button(self, text: str, tooltip: str, slot: Callable[[], object]) -> QPushButton:
        """Tworzy przycisk toolbaru z tooltipem podpiętym do slotu."""
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.clicked.connect(slot)
        return button

    # ── Wczytywanie ─────────────────────────────────────────────────────────--

    def _on_path_changed(self, text: str) -> None:
        """Wczytuje EPUB, gdy ścieżka wskazuje istniejący plik (z obsługą zmian)."""
        path = Path(text)
        if not text or not path.is_file() or path == self._epub_path:
            return
        if not self._confirm_discard():
            return
        self.load_epub(path)

    def load_epub(self, path: Path) -> None:
        """Otwiera EPUB i wczytuje jego spis treści do edytora."""
        self._close_epub()
        try:
            epub = Epub(path)
            epub.open()
        except Exception as exc:
            self.status_label.setText(_("Nie udało się otworzyć: {error}").format(error=exc))
            return
        try:
            entries, source = read_toc(epub)
        except ResourceLimitError:
            epub.close()
            self._show_resource_limit()
            self._refresh_actions()
            return
        self._epub = epub
        self._epub_path = path
        self._entries = entries
        self._dirty = False
        self._rebuild_tree()
        self.status_label.setText(
            _("Wczytano spis ({source}): {count}").format(source=source, count=self._count_label())
        )
        self._refresh_actions()

    # ── Drzewo (model → widok) ──────────────────────────────────────────────--

    def _rebuild_tree(self) -> None:
        """Przebudowuje widok z modelu (problemy na czerwono); sygnały zablokowane."""
        problems = self._problem_map()
        self.tree.blockSignals(True)
        self.tree.clear()
        self._items = {}
        for entry in self._entries:
            self.tree.addTopLevelItem(self._make_item(entry, problems))
        self.tree.expandAll()
        self.tree.blockSignals(False)

    def _make_item(self, entry: TocEntry, problems: dict[str, str]) -> QTreeWidgetItem:
        """Buduje pozycję drzewa dla wpisu (i jego dzieci); mapuje item↔entry."""
        item = QTreeWidgetItem([entry.title, entry.href])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setData(0, _ENTRY_ROLE, id(entry))
        self._items[id(entry)] = entry
        reason = problems.get(entry.href) if entry.href else None
        if reason is not None:
            color = QColor(self._theme.red)
            item.setForeground(_TITLE_COL, color)
            item.setForeground(_TARGET_COL, color)
            item.setToolTip(_TARGET_COL, reason)
        for child in entry.children:
            item.addChild(self._make_item(child, problems))
        return item

    def _problem_map(self) -> dict[str, str]:
        """Mapuje cel → powód problemu (martwy link / brak fragmentu)."""
        if self._epub is None:
            return {}
        return {problem.href: problem.reason for problem in validate_toc(self._epub, self._entries)}

    def _selected_entry(self) -> TocEntry | None:
        """Zwraca wpis odpowiadający zaznaczonej pozycji (lub ``None``)."""
        item = cast("QTreeWidgetItem | None", self.tree.currentItem())
        if item is None:
            return None
        return self._items.get(item.data(0, _ENTRY_ROLE))

    # ── Edycja tytułu / przenoszenie ─────────────────────────────────────────

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Edycja tytułu wyłącznie w kolumnie tytułu (kolumna celu jest tylko do odczytu)."""
        if column == _TITLE_COL:
            self.tree.editItem(item, _TITLE_COL)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Przepisuje zmieniony tytuł do modelu (kolumna celu ignorowana)."""
        if column != _TITLE_COL:
            return
        entry = self._items.get(item.data(0, _ENTRY_ROLE))
        if entry is not None and entry.title != item.text(_TITLE_COL):
            entry.title = item.text(_TITLE_COL)
            self._mark_dirty()

    def _on_move_requested(
        self, source: QTreeWidgetItem, target: QTreeWidgetItem, mode: str
    ) -> None:
        """Mapuje pozycje widoku na wpisy modelu i wykonuje przeniesienie."""
        src = self._items.get(source.data(0, _ENTRY_ROLE))
        dst = self._items.get(target.data(0, _ENTRY_ROLE))
        if src is not None and dst is not None:
            self._handle_move(src, dst, mode)

    def _handle_move(self, src: TocEntry, dst: TocEntry, mode: str) -> None:
        """Wykonuje przeniesienie na modelu i przebudowuje widok (testowalne)."""
        try:
            move_entry(self._entries, src, dst, mode)  # type: ignore[arg-type]
        except ValueError:
            return  # np. próba przeniesienia do własnego potomka — ignorujemy
        except ResourceLimitError:
            self._show_resource_limit()
            return
        self._mark_dirty()
        self._rebuild_tree()

    def _reorder(self, direction: str) -> None:
        """Przesuwa zaznaczony wpis: up/down (rodzeństwo) lub in/out (poziom)."""
        entry = self._selected_entry()
        if entry is None:
            return
        try:
            siblings = siblings_of(self._entries, entry)
        except ResourceLimitError:
            self._show_resource_limit()
            return
        if siblings is None:
            return
        items, index = siblings
        if direction == "up" and index > 0:
            self._handle_move(entry, items[index - 1], "before")
        elif direction == "down" and index < len(items) - 1:
            self._handle_move(entry, items[index + 1], "after")
        elif direction == "in" and index > 0:
            self._handle_move(entry, items[index - 1], "into")
        elif direction == "out":
            try:
                parent = parent_of(self._entries, entry)
            except ResourceLimitError:
                self._show_resource_limit()
                return
            if parent is not None:
                self._handle_move(entry, parent, "after")

    def _add_entry(self) -> None:
        """Dodaje nową pozycję jako rodzeństwo zaznaczonej (lub na końcu listy)."""
        new_entry = TocEntry(title=_("Nowa pozycja"), href="")
        selected = self._selected_entry()
        try:
            siblings = siblings_of(self._entries, selected) if selected is not None else None
        except ResourceLimitError:
            self._show_resource_limit()
            return
        if siblings is not None:
            items, index = siblings
            insert_at = index + 1
        else:
            items = self._entries
            insert_at = len(items)
        items.insert(insert_at, new_entry)
        try:
            validate_toc_structure(self._entries)
        except ResourceLimitError:
            items.pop(insert_at)
            self._show_resource_limit()
            return
        self._mark_dirty()
        self._rebuild_tree()

    def _remove_entry(self) -> None:
        """Usuwa zaznaczony wpis wraz z poddrzewem."""
        entry = self._selected_entry()
        if entry is None:
            return
        try:
            siblings = siblings_of(self._entries, entry)
        except ResourceLimitError:
            self._show_resource_limit()
            return
        if siblings is not None:
            items, index = siblings
            items.pop(index)
            self._mark_dirty()
            self._rebuild_tree()

    # ── Generowanie / naprawa / zapis ─────────────────────────────────────────

    def _generate(self) -> None:
        """Generuje spis z nagłówków po potwierdzeniu nadpisania bieżącego."""
        if self._epub is None:
            return
        if self._entries and not self._confirm(_("Zastąpić bieżący spis treści wygenerowanym?")):
            return
        try:
            generated = generate_toc(self._epub, max_level=self.level_spin.value())
        except ResourceLimitError:
            self._show_resource_limit()
            return
        self._entries = generated
        self._mark_dirty()
        self._rebuild_tree()
        self.status_label.setText(_("Wygenerowano spis: {count}").format(count=self._count_label()))

    def _repair(self) -> None:
        """Pokazuje listę problemów i po potwierdzeniu usuwa martwe wpisy."""
        if self._epub is None:
            return
        try:
            problems = validate_toc(self._epub, self._entries)
        except ResourceLimitError:
            self._show_resource_limit()
            return
        if not problems:
            self.status_label.setText(_("Spis treści jest poprawny."))
            return
        if not self._show_problems_dialog(problems):
            return
        try:
            repaired, removed = repair_toc(self._epub, self._entries)
        except ResourceLimitError:
            self._show_resource_limit()
            return
        self._entries = repaired
        self._mark_dirty()
        self._rebuild_tree()
        self.status_label.setText(_("Usunięto {n} wpisów.").format(n=len(removed)))

    def _save(self) -> None:
        """Zapisuje spis (nav + ncx) do EPUB-a (z kopią .bak)."""
        if self._epub is None or self._epub_path is None:
            return
        try:
            write_toc(self._epub, self._entries)
            self._epub.save()
        except ResourceLimitError:
            self._show_resource_limit()
            return
        except Exception as exc:
            self.status_label.setText(_("Nie udało się zapisać: {error}").format(error=exc))
            return
        self._dirty = False
        self._rebuild_tree()
        self.status_label.setText(_("Zapisano spis treści do EPUB."))
        self._refresh_actions()

    def _show_problems_dialog(self, problems: list[TocProblem]) -> bool:
        """Pokazuje dialog z listą problemów; zwraca True, gdy użytkownik potwierdzi."""
        dialog = QDialog(self)
        dialog.setWindowTitle(_("Problemy spisu treści"))
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(_("Znalezione martwe wpisy zostaną usunięte:")))
        listing = QTreeWidget()
        listing.setHeaderLabels([_("Cel"), _("Powód")])
        for problem in problems:
            listing.addTopLevelItem(QTreeWidgetItem([problem.href, problem.reason]))
        layout.addWidget(listing)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.resize(520, 320)
        return dialog.exec() == QDialog.DialogCode.Accepted

    # ── Stan / pomocnicze ─────────────────────────────────────────────────────

    def _count_label(self) -> str:
        """Etykieta liczby pozycji (z formą mnogą)."""
        from epubforge.toc import iter_entries

        count = sum(1 for _entry in iter_entries(self._entries))
        return ngettext("{n} pozycja", "{n} pozycji", count).format(n=count)

    def _show_resource_limit(self) -> None:
        """Pokazuje bezpieczny, wspólny komunikat o limicie struktury TOC."""
        self.status_label.setText(
            _("Spis treści jest zbyt duży lub zbyt głęboki do bezpiecznego przetworzenia.")
        )

    def _mark_dirty(self) -> None:
        """Oznacza niezapisane zmiany i odświeża pasek/akcje."""
        self._dirty = True
        self._refresh_actions()

    def _refresh_actions(self) -> None:
        """Włącza akcje zależnie od wczytanego pliku i stanu zmian."""
        loaded = self._epub is not None
        for button in (
            self.generate_button,
            self.repair_button,
            self.add_button,
            self.remove_button,
            self.up_button,
            self.down_button,
            self.outdent_button,
            self.indent_button,
        ):
            button.setEnabled(loaded)
        self.level_spin.setEnabled(loaded)
        self.save_button.setEnabled(loaded and self._dirty)

    def has_unsaved_changes(self) -> bool:
        """Czy są niezapisane zmiany spisu treści."""
        return self._dirty

    def set_theme(self, theme: Theme) -> None:
        """Aktualizuje motyw i przemalowuje wiersze drzewa."""
        self._theme = theme
        self._rebuild_tree()

    def _confirm(self, question: str) -> bool:
        """Pyta tak/nie; zwraca True przy potwierdzeniu."""
        answer = QMessageBox.question(
            self,
            _("Potwierdzenie"),
            question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _confirm_discard(self) -> bool:
        """Przy niezapisanych zmianach pyta o porzucenie przed zmianą pliku."""
        if not self._dirty:
            return True
        return self._confirm(_("Spis treści ma niezapisane zmiany. Porzucić je?"))

    def _close_epub(self) -> None:
        """Zamyka bieżący EPUB i czyści stan."""
        if self._epub is not None:
            self._epub.close()
        self._epub = None
        self._epub_path = None
        self._entries = []
        self._items = {}
        self._dirty = False
