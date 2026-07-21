"""Zakładka „Edytor" — przegląd i szybka edycja plików wewnątrz EPUB (F3 core).

Quick fix, nie Sigil: jeden otwarty :class:`Epub` na życie zakładki, drzewo plików
po grupach, edytor z podświetlaniem dla XML/CSS, podgląd obrazów, panel info dla
binariów. Start w trybie tylko-do-odczytu; edycja po włączeniu „Trybu edycji".

Klasyfikacja/dekodowanie/pozycje są w :mod:`epubforge.gui.editor_files` (czyste,
testowalne bez Qt). Tu jest tylko UI i przepływ zapisu.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

from chodzkos_gui_kit.palette import Palette as Theme
from chodzkos_gui_kit.qt.dialogs import open_file
from chodzkos_gui_kit.qt.theme import current_palette as current_theme
from lxml import etree
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMessageBox,
    QTreeWidgetItem,
    QWidget,
)

from epubforge.core import ConfigStore, Epub, Tool
from epubforge.core._xml_safe import XmlSecurityError, parse_untrusted
from epubforge.gui import editor_files as ef
from epubforge.gui.preview import PreviewSession, PreviewSettings
from epubforge.gui.tabs.editor_layout import EditorLayoutMixin
from epubforge.gui.tabs.editor_preview import (
    _PAGE_EDITOR,
    _PAGE_IMAGE,
    _PAGE_INFO,
    EditorPreviewMixin,
)
from epubforge.i18n import _

logger = logging.getLogger(__name__)

_PATH_ROLE = Qt.ItemDataRole.UserRole


def _group_label(key: str) -> str:
    """Lokalizowana etykieta grupy drzewa dla klucza z :mod:`editor_files`."""
    return {
        ef.GROUP_TEXT: _("Tekst"),
        ef.GROUP_STYLE: _("Style"),
        ef.GROUP_IMAGE: _("Obrazy"),
        ef.GROUP_FONT: _("Fonty"),
        ef.GROUP_OTHER: _("Inne"),
    }.get(key, key)


class EditorTab(EditorLayoutMixin, EditorPreviewMixin, QWidget):
    """Przegląd i edycja zawartości EPUB z podświetlaniem składni.

    Prawy panel (inspektor CSS + podgląd HTML + przełącznik Kod/Podgląd) jest
    w :class:`~epubforge.gui.tabs.editor_preview.EditorPreviewMixin`.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tools: dict[str, Tool] | None = None,
        config: ConfigStore | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme: Theme = current_theme()
        self._tools = tools if tools is not None else {}
        # Ustawienia podglądu w istniejącym ConfigStore (bez drugiego pliku/timera);
        # bez configu (część testów) działają na ulotnym słowniku.
        self._preview_settings = PreviewSettings(config)
        self._epub: Epub | None = None
        self._epub_path: Path | None = None
        self._dirty: dict[str, str] = {}  # ścieżka → tekst zapisany do bufora EPUB
        self._current: str | None = None
        self._readonly_files: set[str] = set()  # pliki z bajtami zastępczymi
        self._media_types: dict[str, str] = {}
        self._switching = False  # blokada rekurencji przy cofaniu zaznaczenia

        self._make_preview_timer()
        self._build_ui()
        self._wire_shortcuts()
        self._refresh_actions()
        self._update_mode_indicator()

    def _wire_shortcuts(self) -> None:
        save = QShortcut(QKeySequence.StandardKey.Save, self)
        save.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        save.activated.connect(self._save_current)
        search = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        search.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        search.activated.connect(self._toggle_search_panel)

    def _toggle_search_panel(self) -> None:
        """Pokazuje/ukrywa panel Szukaj/Zamień (Ctrl+Shift+F)."""
        self.search_panel.toggle()

    # ── Kontrakt panelu Szukaj/Zamień (SearchHost) ────────────────────────────

    def search_epub_instance(self) -> Epub | None:
        """Zwraca otwarty EPUB dla panelu Szukaj/Zamień."""
        return self._epub

    def current_internal_path(self) -> str | None:
        """Zwraca ścieżkę aktualnie wyświetlanego pliku."""
        return self._current

    def flush_current_editor(self) -> None:
        """Zapisuje niezapisane zmiany bieżącego pliku do bufora EPUB (sync _dirty).

        Bez walidacji XML i bez pytań — to cichy sync przed „Zamień wszystkie",
        żeby zamiana działała na treści widocznej w edytorze (pułapka Etapu 21).
        """
        if self._epub is None or self._current is None or self.code_editor.read_only:
            return
        if not self.code_editor.is_modified():
            return
        text = self.code_editor.get_text()
        self._epub.write_file(self._current, text.encode("utf-8"))
        self._dirty[self._current] = text
        self.code_editor.editor.document().setModified(False)

    def jump_to_hit(self, internal_path: str, line: int, column: int) -> None:
        """Otwiera plik w edytorze i ustawia kursor na trafieniu (reuse skoku)."""
        self._select_path(internal_path)
        if self.stack.currentIndex() == _PAGE_EDITOR:
            self.code_editor.goto_position(line, column)

    def mark_replaced(self, paths: list[str]) -> None:
        """Oznacza pliki zmienione przez „Zamień wszystkie" i odświeża widok.

        ``replace_in_epub`` pisze prosto do bufora EPUB, z pominięciem ``_dirty``
        zakładki — uzupełniamy je, by „Zapisz EPUB" i znaczniki „*" działały.
        """
        if self._epub is None:
            return
        for internal in paths:
            text, _replaced = ef.decode_text(self._epub.read_file(internal))
            self._dirty[internal] = text
        if self._current in paths:
            self._show_file(self._current)
        self._update_tree_markers()
        self._refresh_actions()

    # ── Otwieranie EPUB ─────────────────────────────────────────────────────--

    def _choose_epub(self) -> None:
        """Wybór pliku EPUB przez dialog i otwarcie go."""
        path = open_file(self, _("Otwórz EPUB"), "", _("Pliki EPUB (*.epub)"))
        if path:
            self.open_epub(Path(path))

    def open_epub(self, path: Path) -> bool:
        """Otwiera EPUB (pyta o niezapisane zmiany bieżącego). Zwraca sukces."""
        if not self._confirm_discard_epub():
            return False
        try:
            epub = Epub(path)
            epub.open()
        except Exception as exc:
            QMessageBox.critical(
                self, _("Błąd"), _("Nie udało się otworzyć EPUB:\n{e}").format(e=exc)
            )
            return False
        self._close_epub()
        self._epub = epub
        self._epub_path = path
        self.path_label.setText(str(path))
        self.path_label.setToolTip(str(path))
        # Nowa publikacja → osobna sesja podglądu (origin per sesja: Prompt 2).
        self.book_preview.set_session(PreviewSession.create(epub, path))
        self._populate_tree()
        self._refresh_actions()
        return True

    def open_external(
        self, epub_path: Path, internal_path: str | None = None, line: int | None = None
    ) -> None:
        """Kontrakt dla F-E/F-D: otwórz EPUB (jeśli inny), zaznacz plik, idź do linii."""
        needs_open = self._epub_path != epub_path or self._epub is None
        if needs_open and not self.open_epub(epub_path):
            return
        if internal_path is not None:
            self._select_path(internal_path)
        if line is not None and self.stack.currentIndex() == _PAGE_EDITOR:
            self.code_editor.goto_line(line)

    # ── Drzewo plików ─────────────────────────────────────────────────────────

    def _populate_tree(self) -> None:
        """Buduje drzewo plików pogrupowane wg media-type/rozszerzenia."""
        self.tree.clear()
        self._media_types = {}
        if self._epub is None:
            return
        opf_dir = self._epub.opf_dir()
        for item in self._epub.manifest:
            internal = ef.resolve_internal_path(item.href, opf_dir)
            self._media_types[internal] = item.media_type

        grouped: dict[str, list[str]] = {key: [] for key in ef.GROUP_ORDER}
        for internal in self._all_files():
            grouped[ef.classify(internal, self._media_types.get(internal))].append(internal)

        for key in ef.GROUP_ORDER:
            paths = sorted(grouped[key])
            if not paths:
                continue
            group_item = QTreeWidgetItem([_group_label(key)])
            group_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            group_item.setToolTip(0, _group_label(key))
            self.tree.addTopLevelItem(group_item)
            for internal in paths:
                child = QTreeWidgetItem([self._display_name(internal)])
                child.setData(0, _PATH_ROLE, internal)
                child.setToolTip(0, internal)
                group_item.addChild(child)
            group_item.setExpanded(True)
        self._update_tree_markers()
        self.tree.resizeColumnToContents(0)

    def _all_files(self) -> list[str]:
        """Wszystkie pliki EPUB poza ``mimetype`` i metadanymi kontenera."""
        if self._epub is None:
            return []
        skip = {"mimetype", "META-INF/container.xml"}
        return [name for name in self._epub.list_files() if name not in skip]

    def _file_items(self) -> Iterator[QTreeWidgetItem]:
        """Iteruje po pozycjach plików w drzewie (pomija puste grupy)."""
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            if group is None:
                continue
            for child_index in range(group.childCount()):
                child = group.child(child_index)
                if child is not None:
                    yield child

    def _select_path(self, internal: str) -> None:
        """Zaznacza w drzewie pozycję o danej ścieżce wewnętrznej."""
        for child in self._file_items():
            if child.data(0, _PATH_ROLE) == internal:
                self.tree.setCurrentItem(child)
                return

    def _on_item_changed(
        self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None
    ) -> None:
        """Zmiana zaznaczenia: pyta o niezapisane zmiany, ładuje plik (lub cofa)."""
        if self._switching or current is None:
            return
        internal = current.data(0, _PATH_ROLE)
        if internal is None or internal == self._current:
            return
        if not self._confirm_discard_current():
            self._revert_selection(previous)
            return
        self._show_file(internal)

    def _revert_selection(self, previous: QTreeWidgetItem | None) -> None:
        """Cofa zaznaczenie do poprzedniej pozycji bez ponownego pytania."""
        self._switching = True
        if previous is not None:
            self.tree.setCurrentItem(previous)
        else:
            self.tree.clearSelection()
        self._switching = False

    # ── Wyświetlanie pliku ─────────────────────────────────────────────────--

    def _show_file(self, internal: str) -> None:
        """Pokazuje plik we właściwym panelu (edytor/obraz/info)."""
        if self._epub is None:
            return
        self._current = internal
        media_type = self._media_types.get(internal)
        data = self._epub.read_file(internal)

        if ef.is_image(internal, media_type):
            self.image_preview.show_data(data)
            self.stack.setCurrentIndex(_PAGE_IMAGE)
            self.view_switch.setVisible(False)
            self._set_info_bar("")
        elif ef.is_editable(internal, media_type):
            self._show_in_editor(internal, media_type, data)
        else:
            self.info_panel.setText(self._binary_info(internal, media_type, len(data)))
            self.stack.setCurrentIndex(_PAGE_INFO)
            self.view_switch.setVisible(False)
            self._set_info_bar("")
        self._update_inspector()
        # W trybie dzielonym: podgląd obok pokazuj tylko dla HTML (inaczej ukryj).
        self._sync_split_preview()

    def _show_in_editor(self, internal: str, media_type: str | None, data: bytes) -> None:
        """Ładuje tekst do edytora; bajty zastępcze ⇒ wymuszony read-only."""
        text, replaced = ef.decode_text(data)
        if replaced:
            self._readonly_files.add(internal)
            self._set_info_bar(_("Plik zawiera znaki nie-UTF-8 — edycja zablokowana."))
        else:
            self._readonly_files.discard(internal)
            self._set_info_bar("")
        self.code_editor.load(text, ef.profile_for(internal, media_type))
        self.stack.setCurrentIndex(_PAGE_EDITOR)
        self._apply_read_only()
        self._update_view_switch(internal, media_type)

    # ── Edycja / zapis ─────────────────────────────────────────────────────--

    def _on_edit_toggled(self, _checked: bool) -> None:
        """Przełącza tryb edycji, aktualizuje read-only i sygnalizację trybu."""
        self._apply_read_only()
        self._update_mode_indicator()

    def _update_mode_indicator(self) -> None:
        """Wzmacnia sygnał trybu: etykieta przełącznika i status w kolorze motywu.

        Tryb jest pamiętany per sesja (nie per plik) — przełącznik nie resetuje się
        przy zmianie pliku. Obwódka edytora (akcent w edycji) jest sterowana przez
        ``CodeEditor`` ze stanu read-only, więc pliki nie-UTF-8 pozostają bez akcentu.
        """
        editing = self.edit_toggle.isChecked()
        self.edit_toggle.setText(_("Tryb: edycja") if editing else _("Tryb: tylko podgląd"))
        if editing:
            self.mode_label.setText(_("● Edycja"))
            color = self._theme.accent
        else:
            self.mode_label.setText(_("● Tylko podgląd"))
            color = self._theme.fg2
        self.mode_label.setStyleSheet(f"QLabel {{ color: {color}; }}")

    def _apply_read_only(self) -> None:
        """Edytor jest edytowalny tylko w trybie edycji i dla plików bez zastępczych."""
        forced = self._current in self._readonly_files if self._current else False
        self.code_editor.read_only = not self.edit_toggle.isChecked() or forced

    def _on_modified(self, _modified: bool) -> None:
        """Reaguje na zmianę stanu modyfikacji edytora (znacznik „*", akcje)."""
        self._update_tree_markers()
        self._refresh_actions()

    def _save_current(self) -> bool:
        """Ctrl+S: waliduje (XML), zapisuje bieżący plik do bufora EPUB."""
        if self._epub is None or self._current is None or self.code_editor.read_only:
            return False
        if not self.code_editor.is_modified() and self._current not in self._readonly_files:
            return True
        text = self.code_editor.get_text()
        if not self._validate_xml(self._current, text):
            return False
        self._epub.write_file(self._current, text.encode("utf-8"))
        self._dirty[self._current] = text
        self.code_editor.editor.document().setModified(False)
        self._update_tree_markers()
        self._refresh_actions()
        return True

    def _validate_xml(self, internal: str, text: str) -> bool:
        """Dla profilu XML sprawdza poprawność; przy błędzie pyta „Zapisać mimo to?"."""
        if ef.profile_for(internal, self._media_types.get(internal)) != ef.PROFILE_XML:
            return True
        try:
            # Walidacja strict przez centralny utwardzony parser (XXE/encje off).
            parse_untrusted(text.encode("utf-8"))
        except (etree.XMLSyntaxError, XmlSecurityError) as exc:
            answer = QMessageBox.question(
                self,
                _("Niepoprawny XML"),
                _("Plik nie jest poprawnym XML:\n{e}\n\nZapisać mimo to?").format(e=exc),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            return answer == QMessageBox.StandardButton.Yes
        return True

    def _save_epub(self) -> None:
        """„Zapisz EPUB": utrwala bufor na dysk (z backupem .bak), resetuje wskaźniki."""
        if self._epub is None or not self._dirty:
            return
        try:
            self._epub.save()
        except Exception as exc:
            QMessageBox.critical(
                self, _("Błąd"), _("Nie udało się zapisać EPUB:\n{e}").format(e=exc)
            )
            return
        self._dirty.clear()
        self._update_tree_markers()
        self._refresh_actions()

    def _confirm_discard_current(self) -> bool:
        """Przy niezapisanych zmianach bieżącego pliku pyta Zapisz/Porzuć/Anuluj."""
        if self._current is None or not self.code_editor.is_modified():
            return True
        answer = QMessageBox.question(
            self,
            _("Niezapisane zmiany"),
            _("Plik „{name}” ma niezapisane zmiany.").format(name=self._current),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self._save_current()
        return answer == QMessageBox.StandardButton.Discard

    def _confirm_discard_epub(self) -> bool:
        """Przy niezapisanych zmianach EPUB pyta o zapis przed otwarciem innego."""
        if not self.has_unsaved_changes():
            return True
        answer = QMessageBox.question(
            self,
            _("Niezapisane zmiany"),
            _("EPUB ma niezapisane zmiany. Zapisać przed zamknięciem?"),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            self._save_current()
            self._save_epub()
            return True
        return answer == QMessageBox.StandardButton.Discard

    # ── Stan / pomocnicze ─────────────────────────────────────────────────────

    def has_unsaved_changes(self) -> bool:
        """Czy są zmiany niezapisane na dysk (bufor EPUB lub bieżący edytor)."""
        return bool(self._dirty) or self.code_editor.is_modified()

    def set_theme(self, theme: Theme) -> None:
        """Przekazuje motyw do edytora, inspektora CSS i chrome podglądu.

        Podgląd przemalowuje wyłącznie chrome — treść książki NIE jest renderowana
        ponownie przy zmianie motywu aplikacji.
        """
        self._theme = theme
        self.code_editor.set_theme(theme)
        self.css_inspector.set_theme(theme)
        self.book_preview.set_theme(theme)
        self._update_mode_indicator()

    def _close_epub(self) -> None:
        """Zamyka bieżący EPUB i czyści stan edycji."""
        # Najpierw unieważnij origin, żeby żaden request nie przeżył zamknięcia ZIP-a.
        self.book_preview.set_session(None)
        if self._epub is not None:
            self._epub.close()
        self._epub = None
        self._dirty.clear()
        self._readonly_files.clear()
        self._current = None

    def dispose(self) -> None:
        """Unieważnia sesję, zamyka EPUB i zwalnia oba backendy podglądu."""
        self._preview_timer.stop()
        self._close_epub()
        self.book_preview.dispose()

    def _update_tree_markers(self) -> None:
        """Dokleja „*" do nazw zmodyfikowanych plików w drzewie."""
        for child in self._file_items():
            internal = child.data(0, _PATH_ROLE)
            child.setText(0, self._display_name(internal))
        self.tree.resizeColumnToContents(0)

    def _display_name(self, internal: str) -> str:
        """Nazwa pliku w drzewie z „*", gdy zmodyfikowany (bufor lub bieżący edytor)."""
        name = internal.rsplit("/", 1)[-1]
        modified = internal in self._dirty or (
            internal == self._current and self.code_editor.is_modified()
        )
        return f"{name} *" if modified else name

    def _refresh_actions(self) -> None:
        """Aktualizuje stan przycisku „Zapisz EPUB" i wskaźnika niezapisanych zmian."""
        self.save_epub_button.setEnabled(bool(self._dirty))
        self.open_button.setEnabled(True)

    def _set_info_bar(self, text: str) -> None:
        """Pokazuje/ukrywa pasek informacyjny pliku."""
        self.info_bar.setText(text)
        self.info_bar.setVisible(bool(text))

    def _binary_info(self, internal: str, media_type: str | None, size: int) -> str:
        """Tekst panelu info dla plików nieedytowalnych."""
        return _("{name}\n\nTyp: {mtype}\nRozmiar: {size} B").format(
            name=internal, mtype=media_type or _("nieznany"), size=size
        )
