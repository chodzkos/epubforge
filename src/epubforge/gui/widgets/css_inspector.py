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
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from epubforge.fixers.css_rules import (
    CssRuleInfo,
    build_preview_html,
    parse_rules,
    parse_single_rule,
)
from epubforge.gui.widgets.code_editor import CodeEditor
from epubforge.i18n import _

# Kolory „papieru" podglądu — CELOWO niezależne od motywu aplikacji (symulacja
# kartki książki); jedyny wyjątek od zasady „kolory tylko z Theme".
_PAPER_BG = "#ffffff"
_PAPER_FG = "#1a1a1a"

_PREVIEW_DEBOUNCE_MS = 300
_REFRESH_DEBOUNCE_MS = 400
_DECL_SHORTCUT_MAX = 60
_INDEX_ROLE = Qt.ItemDataRole.UserRole


class CssInspector(QWidget):
    """Panel: lista reguł + edytor reguły + podgląd na żywo + Zastosuj."""

    rule_applied = Signal()

    def __init__(
        self,
        get_source: Callable[[], str],
        apply_replacement: Callable[[int, int, str], None] | None = None,
        theme: Theme | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._get_source = get_source
        self._apply = apply_replacement  # None → tryb tylko do odczytu
        self._theme = theme if theme is not None else current_theme()
        self._rules: list[CssRuleInfo] = []
        self._source = ""
        self._index = -1
        self._last_good_html = ""

        self._preview_timer = _single_shot(self, _PREVIEW_DEBOUNCE_MS, self._update_preview)
        self._refresh_timer = _single_shot(self, _REFRESH_DEBOUNCE_MS, self.refresh)

        self._build_ui()
        self._style_preview()
        self.refresh()

    # ── Budowa UI ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([_("Selektor"), _("Deklaracje"), _("@media")])
        self.tree.setRootIsDecorated(False)
        self.tree.currentItemChanged.connect(self._on_rule_selected)
        splitter.addWidget(self.tree)

        read_only = self._apply is None
        self.rule_editor = CodeEditor()
        self.rule_editor.read_only = read_only
        self.rule_editor.editor.textChanged.connect(self._preview_timer.start)
        splitter.addWidget(self.rule_editor)

        splitter.addWidget(self._build_preview_pane())
        splitter.setSizes([220, 150, 230])

        buttons = QHBoxLayout()
        self.apply_button = QPushButton(_("Zastosuj do arkusza"))
        self.apply_button.clicked.connect(self._apply_rule)
        self.revert_button = QPushButton(_("Przywróć"))
        self.revert_button.clicked.connect(self._revert_rule)
        buttons.addStretch(1)
        buttons.addWidget(self.revert_button)
        buttons.addWidget(self.apply_button)
        self.apply_button.setVisible(not read_only)
        self.revert_button.setVisible(not read_only)
        layout.addLayout(buttons)

    def _build_preview_pane(self) -> QWidget:
        pane = QWidget()
        box = QVBoxLayout(pane)
        box.setContentsMargins(0, 0, 0, 0)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
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
        """Re-parsuje źródło i odbudowuje listę reguł (zaznaczenie po selektorze)."""
        previous_selector = (
            self._rules[self._index].selector if 0 <= self._index < len(self._rules) else None
        )
        self._source = self._get_source()
        self._rules = parse_rules(self._source)

        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        items: list[QTreeWidgetItem] = []
        for index, rule in enumerate(self._rules):
            item = QTreeWidgetItem([rule.selector, _decl_shortcut(rule), rule.media or ""])
            item.setData(0, _INDEX_ROLE, index)
            if not rule.previewable:
                disabled = QColor(self._theme.disabled_fg)
                for column in range(3):
                    item.setForeground(column, disabled)
            items.append(item)
        self.tree.addTopLevelItems(items)
        self.tree.setUpdatesEnabled(True)

        target = _index_for_selector(self._rules, previous_selector)
        selected = self.tree.topLevelItem(target) if target is not None else None
        if selected is not None:
            self.tree.setCurrentItem(selected)

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

    def set_theme(self, theme: Theme) -> None:
        """Aktualizuje motyw (edytor reguły, kolor wyszarzenia, ramka podglądu)."""
        self._theme = theme
        self.rule_editor.set_theme(theme)
        self._style_preview()
        self.refresh()

    def _style_preview(self, error: bool = False) -> None:
        """Stylizuje kartę podglądu: biały papier, ramka z motywu (czerwona przy błędzie)."""
        border = self._theme.red if error else self._theme.border
        self.preview.setStyleSheet(
            f"QTextEdit {{ background-color: {_PAPER_BG}; color: {_PAPER_FG}; "
            f"border: 1px solid {border}; }}"
        )


def _single_shot(parent: QWidget, interval: int, slot: Callable[[], None]) -> QTimer:
    """Tworzy jednostrzałowy QTimer podpięty do slotu (debounce)."""
    timer = QTimer(parent)
    timer.setSingleShot(True)
    timer.setInterval(interval)
    timer.timeout.connect(slot)
    return timer


def _decl_shortcut(rule: CssRuleInfo) -> str:
    """Skrót deklaracji reguły do ~60 znaków dla kolumny listy."""
    text = "; ".join(f"{decl.name}: {decl.value}" for decl in rule.declarations)
    return text if len(text) <= _DECL_SHORTCUT_MAX else text[: _DECL_SHORTCUT_MAX - 1] + "…"


def _index_for_selector(rules: list[CssRuleInfo], selector: str | None) -> int | None:
    """Indeks pierwszej reguły o danym selektorze; fallback na pierwszą regułę."""
    if not rules:
        return None
    if selector is not None:
        for index, rule in enumerate(rules):
            if rule.selector == selector:
                return index
    return 0
