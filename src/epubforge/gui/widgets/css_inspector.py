"""Inspektor reguł CSS z podglądem na żywo (F3+).

Lista reguł arkusza; dla wybranej — edytor reguły i podgląd przykładowego tekstu
sformatowanego zgodnie z regułą (silnik rich text Qt). Edycja aktualizuje podgląd
z debounce; „Zastosuj" wpisuje zmianę do arkusza przez ``apply_replacement``
(jedyna ścieżka zapisu — podmiana po spanie).

Podgląd renderujemy na **białej „papierowej" karcie niezależnej od motywu** — tryb
ciemny aplikacji nie może fałszować typografii książki.
"""

from __future__ import annotations

from collections.abc import Callable

from chodzkos_gui_kit.palette import Palette as Theme
from chodzkos_gui_kit.qt.theme import current_palette as current_theme
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from epubforge.fixers.css_rules import (
    CssRuleInfo,
    CssRuleParseResult,
    build_preview_html,
    parse_rules_bounded,
    parse_single_rule,
)
from epubforge.gui.css_inspection import (
    ElementInspection,
    RuleIdentity,
    SourceProvider,
    content_revision,
    map_element_report,
)
from epubforge.gui.css_inspector_limits import (
    MAX_CSS_INSPECTOR_DECLARATIONS,
    MAX_CSS_INSPECTOR_RULE_DECLARATIONS,
    MAX_CSS_INSPECTOR_RULES,
    MAX_CSS_INSPECTOR_SOURCE_BYTES,
    utf8_fits,
)
from epubforge.gui.widgets.code_editor import CodeEditor
from epubforge.gui.widgets.css_element_panel import CssElementPanel
from epubforge.gui.widgets.css_sheet_format import declaration_shortcut, index_for_rule_key
from epubforge.gui.widgets.css_sheet_loader import CssSheetLoader, CssSheetLoadResult
from epubforge.i18n import _

# Kolory „papieru" podglądu — CELOWO niezależne od motywu aplikacji (symulacja
# kartki książki); jedyny wyjątek od zasady „kolory tylko z Theme".
_PAPER_BG = "#ffffff"
_PAPER_FG = "#1a1a1a"

_PREVIEW_DEBOUNCE_MS = 300
_REFRESH_DEBOUNCE_MS = 400
_INDEX_ROLE = Qt.ItemDataRole.UserRole


class CssInspector(QWidget):
    """Panel: lista reguł + edytor reguły + podgląd na żywo + Zastosuj."""

    RULE_PAGE_SIZE = 500

    rule_applied = Signal()

    def __init__(
        self,
        get_source: Callable[[], str],
        apply_replacement: Callable[[int, int, str], None] | None = None,
        theme: Theme | None = None,
        parent: QWidget | None = None,
        *,
        source_provider: SourceProvider | None = None,
        generation_provider: Callable[[], int] | None = None,
        preview_rule: Callable[[str, str, bool], None] | None = None,
        apply_mapped_rule: Callable[[RuleIdentity, str], bool] | None = None,
        jump_rule: Callable[[RuleIdentity], None] | None = None,
        show_element_source: Callable[[str], None] | None = None,
        create_rule: Callable[[str, str | None], None] | None = None,
        highlight_matches: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._get_source = get_source
        self._apply = apply_replacement  # None → tryb tylko do odczytu
        self._theme = theme if theme is not None else current_theme()
        self._source_provider = source_provider
        self._generation_provider = generation_provider or (lambda: 0)
        self._mapped_apply = apply_mapped_rule or (lambda _identity, _text: False)
        self._rules: list[CssRuleInfo] = []
        self._source = ""
        self._index = -1
        self._last_good_html = ""
        self._source_revision = 0
        self._rendered_rules = 0
        self._pending_rule_key: tuple[tuple[int, ...], tuple[int, int]] | None = None

        self._preview_timer = _single_shot(self, _PREVIEW_DEBOUNCE_MS, self._update_preview)
        self._refresh_timer = _single_shot(self, _REFRESH_DEBOUNCE_MS, self.refresh)

        self._build_ui(
            preview_rule=preview_rule or (lambda _selector, _text, _current: None),
            jump_rule=jump_rule or (lambda _identity: None),
            show_element_source=show_element_source or (lambda _node: None),
            create_rule=create_rule or (lambda _selector, _path: None),
            highlight_matches=highlight_matches or (lambda _selector: None),
        )
        self._sheet_loader = CssSheetLoader(
            parse_rules_bounded,
            self,
            max_rules=MAX_CSS_INSPECTOR_RULES,
            max_declarations=MAX_CSS_INSPECTOR_DECLARATIONS,
            max_rule_declarations=MAX_CSS_INSPECTOR_RULE_DECLARATIONS,
        )
        self._sheet_loader.loaded.connect(self._on_sheet_loaded)
        self._sheet_loader.failed.connect(self._on_sheet_failed)
        self._style_preview()
        self.refresh()

    # ── Budowa UI ─────────────────────────────────────────────────────────────

    def _build_ui(
        self,
        *,
        preview_rule: Callable[[str, str, bool], None],
        jump_rule: Callable[[RuleIdentity], None],
        show_element_source: Callable[[str], None],
        create_rule: Callable[[str, str | None], None],
        highlight_matches: Callable[[str], None],
    ) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.mode_tabs = QTabWidget()
        self.mode_tabs.setToolTip(
            _("Tryb inspektora: arkusz źródłowy albo rzeczywisty element DOM")
        )
        layout.addWidget(self.mode_tabs)

        sheet = QWidget()
        sheet_layout = QVBoxLayout(sheet)
        sheet_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        sheet_layout.addWidget(splitter)
        self.sheet_splitter = splitter

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([_("Selektor"), _("Deklaracje"), _("@media")])
        self.tree.setRootIsDecorated(False)
        self.tree.setToolTip(_("Reguły bieżącego arkusza wraz z deklaracjami i kontekstem @media"))
        self.tree.currentItemChanged.connect(self._on_rule_selected)
        splitter.addWidget(self.tree)

        read_only = self._apply is None
        self.rule_editor = CodeEditor()
        self.rule_editor.setToolTip(
            _("Kod wybranej reguły CSS; zmiany pozostają lokalne do Zastosuj")
        )
        self.rule_editor.read_only = read_only
        self.rule_editor.editor.textChanged.connect(self._preview_timer.start)
        splitter.addWidget(self.rule_editor)

        splitter.addWidget(self._build_preview_pane())
        splitter.setSizes([220, 150, 230])

        self.show_more_button = QPushButton(_("Pokaż więcej"))
        self.show_more_button.setToolTip(_("Pokaż kolejną stronę reguł z pamięci"))
        self.show_more_button.clicked.connect(self._show_more_rules)
        sheet_layout.addWidget(self.show_more_button)
        self.limit_label = QLabel()
        self.limit_label.setWordWrap(True)
        sheet_layout.addWidget(self.limit_label)

        buttons = QHBoxLayout()
        self.apply_button = QPushButton(_("Zastosuj do arkusza"))
        self.apply_button.setToolTip(
            _("Zapisz poprawną regułę do jej dokładnego spanu jako jedną operację Undo")
        )
        self.apply_button.clicked.connect(self._apply_rule)
        self.revert_button = QPushButton(_("Przywróć"))
        self.revert_button.setToolTip(_("Odrzuć edycję reguły i wczytaj ją ponownie ze źródła"))
        self.revert_button.clicked.connect(self._revert_rule)
        buttons.addStretch(1)
        buttons.addWidget(self.revert_button)
        buttons.addWidget(self.apply_button)
        self.apply_button.setVisible(not read_only)
        self.revert_button.setVisible(not read_only)
        sheet_layout.addLayout(buttons)
        self.mode_tabs.addTab(sheet, _("Arkusz"))

        self.element_panel = CssElementPanel(
            source_text=self._mapped_rule_text,
            revision_matches=self._revision_matches,
            preview_rule=preview_rule,
            apply_rule=self._mapped_apply,
            jump_rule=jump_rule,
            show_element_source=show_element_source,
            create_rule=create_rule,
            highlight_matches=highlight_matches,
        )
        self.mode_tabs.addTab(self.element_panel, _("Element"))
        self.mode_tabs.setTabEnabled(1, False)
        for button in self.mode_tabs.findChildren(QToolButton):
            label = _("Przewiń zakładki inspektora w lewo")
            if button.objectName() == "ScrollRightButton":
                label = _("Przewiń zakładki inspektora w prawo")
            button.setToolTip(label)

    def _build_preview_pane(self) -> QWidget:
        pane = QWidget()
        box = QVBoxLayout(pane)
        box.setContentsMargins(0, 0, 0, 0)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setToolTip(_("Przybliżony podgląd wybranej reguły na neutralnej karcie"))
        box.addWidget(self.preview, stretch=1)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        box.addWidget(self.error_label)

        self.unsupported_label = QLabel()
        self.unsupported_label.setWordWrap(True)
        self.unsupported_label.setVisible(False)
        box.addWidget(self.unsupported_label)

        note = QLabel(_("Podgląd przybliżony — czytnik może różnić się w szczegółach."))
        note.setWordWrap(True)
        box.addWidget(note)
        return pane

    # ── Odświeżanie listy ─────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Zamraża źródło; mały model liczy od razu, ciężki przekazuje workerowi."""
        self._pending_rule_key = (
            (self._rules[self._index].rule_path, self._rules[self._index].span)
            if 0 <= self._index < len(self._rules)
            else None
        )
        self._source = self._get_source()
        self._source_revision = content_revision(self._source)
        self._reset_sheet_tree()
        if not utf8_fits(self._source, MAX_CSS_INSPECTOR_SOURCE_BYTES):
            self._sheet_loader.invalidate()
            self.limit_label.setText(
                _("Arkusz CSS jest zbyt duży do bezpiecznej inspekcji. Plik pozostaje bez zmian.")
            )
            return
        self.limit_label.setText(_("Analizowanie arkusza CSS…"))
        self._sheet_loader.request(self._source, self._source_revision)

    def _on_sheet_loaded(self, value: object) -> None:
        """Materializuje wynik tylko dla dokładnego, nadal bieżącego snapshotu."""
        if not isinstance(value, CssSheetLoadResult):
            return
        request = value.request
        if request.revision != self._source_revision or request.source != self._source:
            return
        self._apply_sheet_result(value.parsed)

    def _on_sheet_failed(self, _message: str) -> None:
        """Degraduje błąd parsera bez tracebacku i bez modyfikacji źródła."""
        self._reset_sheet_tree()
        self.limit_label.setText(_("Nie udało się bezpiecznie przeanalizować arkusza CSS."))

    def _apply_sheet_result(self, result: CssRuleParseResult) -> None:
        """Podmienia bounded model i renderuje tylko potrzebne strony."""
        self._rules = list(result.rules)
        self.limit_label.setText(
            _("Inspektor CSS ograniczył liczbę reguł lub deklaracji. Zawęź widok lub użyj filtra.")
            if result.truncated
            else ""
        )
        target = index_for_rule_key(self._rules, self._pending_rule_key)
        pages = 1 if target is None else target // self.RULE_PAGE_SIZE + 1
        self.tree.setUpdatesEnabled(False)
        for _page in range(pages):
            self._show_more_rules()
        self.tree.setUpdatesEnabled(True)

        selected = self.tree.topLevelItem(target) if target is not None else None
        if selected is not None:
            self.tree.setCurrentItem(selected)

    def _reset_sheet_tree(self) -> None:
        """Czyści model prezentacji i stan stron przed nowym snapshotem."""
        self._rules = []
        self._index = -1
        self._rendered_rules = 0
        self.tree.clear()
        self.show_more_button.setEnabled(False)

    def _show_more_rules(self) -> None:
        """Dokłada stronę z istniejącego modelu bez ponownego parsowania CSS."""
        end = min(self._rendered_rules + self.RULE_PAGE_SIZE, len(self._rules))
        items: list[QTreeWidgetItem] = []
        for index in range(self._rendered_rules, end):
            rule = self._rules[index]
            item = QTreeWidgetItem([rule.selector, declaration_shortcut(rule), rule.media or ""])
            item.setData(0, _INDEX_ROLE, index)
            if not rule.previewable:
                disabled = QColor(self._theme.disabled_fg)
                for column in range(3):
                    item.setForeground(column, disabled)
            items.append(item)
        self.tree.addTopLevelItems(items)
        self._rendered_rules = end
        self.show_more_button.setEnabled(end < len(self._rules))

    # ── Wybór / podgląd ────────────────────────────────────────────────────--

    def _on_rule_selected(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        """Ładuje tekst wybranej reguły do edytora i odświeża podgląd."""
        if current is None:
            return
        index = current.data(0, _INDEX_ROLE)
        if not isinstance(index, int) or not 0 <= index < len(self._rules):
            return
        self._index = index
        start, end = self._rules[index].span
        self.rule_editor.load(self._source[start:end], "css")
        self._update_preview()

    def _update_preview(self) -> None:
        """Parsuje tekst edytora reguły i odświeża podgląd (lub pokazuje błąd)."""
        result = parse_single_rule(self.rule_editor.get_text())
        if isinstance(result, list):
            self._show_error(result)
            return
        self.error_label.setVisible(False)
        self._style_preview(error=False)
        html, unsupported = build_preview_html(result)
        self._last_good_html = html
        self.preview.setHtml(html)
        self._show_unsupported(unsupported)

    def _show_error(self, errors: list[str]) -> None:
        """Pokazuje komunikat parsera, zostawiając podgląd na ostatnim poprawnym."""
        self._style_preview(error=True)
        self.error_label.setText(_("Błąd CSS: {msg}").format(msg="; ".join(errors)))
        self.error_label.setVisible(True)

    def _show_unsupported(self, unsupported: list[str]) -> None:
        """Wypisuje deklaracje nieobsługiwane w podglądzie (albo chowa etykietę)."""
        if unsupported:
            self.unsupported_label.setText(
                _("Nieobsługiwane w podglądzie: {items}").format(items=", ".join(unsupported))
            )
            self.unsupported_label.setVisible(True)
        else:
            self.unsupported_label.setVisible(False)

    # ── Zastosuj / przywróć ─────────────────────────────────────────────────--

    def _apply_rule(self) -> None:
        """Waliduje i zapisuje zmianę reguły do arkusza przez ``apply_replacement``."""
        if self._apply is None or not 0 <= self._index < len(self._rules):
            return
        text = self.rule_editor.get_text()
        if isinstance(parse_single_rule(text), list):
            return  # niepoprawny CSS — nie zapisujemy
        if content_revision(self._get_source()) != self._source_revision:
            self._show_error([_("Konflikt revision: źródło zmieniło się; niczego nie nadpisano.")])
            return
        start, end = self._rules[self._index].span
        self._apply(start, end, text)
        self.refresh()
        self.rule_applied.emit()

    def _revert_rule(self) -> None:
        """Przywraca tekst reguły do stanu z arkusza."""
        if 0 <= self._index < len(self._rules):
            start, end = self._rules[self._index].span
            self.rule_editor.load(self._source[start:end], "css")
            self._update_preview()

    # ── Integracja zewnętrzna ─────────────────────────────────────────────────

    def schedule_external_refresh(self) -> None:
        """Planuje odświeżenie po edycji w głównym edytorze (debounce)."""
        self._refresh_timer.start()

    def set_element_report(self, report: object) -> None:
        """Mapuje raport Chromium na aktualne spany i włącza tryb Element."""
        provider = self._source_provider or (lambda _path: None)
        inspection = map_element_report(report, provider, generation=self._generation_provider())
        self.element_panel.set_inspection(inspection)
        self.mode_tabs.setTabEnabled(1, True)
        if inspection.available:
            self.mode_tabs.setCurrentIndex(1)

    def set_element_pending(self) -> None:
        """Czyści poprzedni element podczas przygotowywania aktualnego DOM."""
        self.element_panel.set_inspection(
            ElementInspection(False, error=_("Ładowanie dokumentu do inspektora elementu…"))
        )

    def set_context(self, *, sheet: bool, element: bool) -> None:
        """Włącza tryby właściwe dla bieżącego pliku i aktywnego backendu."""
        self.mode_tabs.setTabEnabled(0, sheet)
        self.mode_tabs.setTabEnabled(1, element)
        if element and not sheet:
            self.mode_tabs.setCurrentIndex(1)
        elif sheet:
            self.mode_tabs.setCurrentIndex(0)

    def set_preview_result(self, result: object) -> None:
        """Przekazuje asynchroniczny wynik warstwy preview do trybu Element."""
        self.element_panel.set_preview_result(result)

    def show_sheet_mode(self) -> None:
        """Przełącza na kompatybilny tryb Arkusz."""
        self.mode_tabs.setCurrentIndex(0)

    def reset(self) -> None:
        """Unieważnia parse/report przy zamknięciu lub podmianie publikacji."""
        self._preview_timer.stop()
        self._refresh_timer.stop()
        self._sheet_loader.invalidate()
        self._source = ""
        self._source_revision = content_revision("")
        self._pending_rule_key = None
        self._reset_sheet_tree()
        self.limit_label.clear()
        self.element_panel.set_inspection(ElementInspection(False))

    def dispose(self) -> None:
        """Kooperacyjnie kończy parser i odrzuca wszystkie późne callbacki."""
        self.reset()
        self._sheet_loader.dispose()

    def set_theme(self, theme: Theme) -> None:
        """Aktualizuje motyw (edytor reguły, kolor wyszarzenia, ramka podglądu)."""
        self._theme = theme
        self.rule_editor.set_theme(theme)
        self.element_panel.rule_editor.set_theme(theme)
        self._style_preview()
        self.refresh()

    def _style_preview(self, error: bool = False) -> None:
        """Stylizuje kartę podglądu: biały papier, ramka z motywu (czerwona przy błędzie)."""
        border = self._theme.red if error else self._theme.border
        self.preview.setStyleSheet(
            f"QTextEdit {{ background-color: {_PAPER_BG}; color: {_PAPER_FG}; "
            f"border: 1px solid {border}; }}"
        )

    def _mapped_rule_text(self, identity: RuleIdentity) -> str | None:
        """Czyta dokładny span wyłącznie z rewizji wskazanej przez tożsamość."""
        if self._source_provider is None:
            return None
        snapshot = self._source_provider(identity.stylesheet_path)
        if snapshot is None or snapshot[1] != identity.revision:
            return None
        source = snapshot[0]
        start, end = identity.span
        return source[start:end] if 0 <= start <= end <= len(source) else None

    def _revision_matches(self, identity: RuleIdentity) -> bool:
        """Chroni Zastosuj przed nadpisaniem nowszej treści arkusza."""
        if self._source_provider is None:
            return False
        snapshot = self._source_provider(identity.stylesheet_path)
        return snapshot is not None and snapshot[1] == identity.revision


def _single_shot(parent: QWidget, interval: int, slot: Callable[[], None]) -> QTimer:
    """Tworzy jednostrzałowy QTimer podpięty do slotu (debounce)."""
    timer = QTimer(parent)
    timer.setSingleShot(True)
    timer.setInterval(interval)
    timer.timeout.connect(slot)
    return timer
