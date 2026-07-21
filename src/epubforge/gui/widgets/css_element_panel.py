"""Widok trybu Element inspektora CSS (bez bezpośredniego importu WebEngine)."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from epubforge.fixers.css_rules import parse_single_rule
from epubforge.gui.css_inspection import ElementInspection, InspectorRule, RuleIdentity
from epubforge.gui.widgets.code_editor import CodeEditor
from epubforge.i18n import _

_RULE_ROLE = Qt.ItemDataRole.UserRole
_TYPOGRAPHY = ("font", "text", "line-", "letter-", "word-", "hyphens", "orphans", "widows")
_LAYOUT = (
    "display",
    "position",
    "inset",
    "top",
    "right",
    "bottom",
    "left",
    "width",
    "height",
    "min-",
    "max-",
    "flex",
    "grid",
    "align",
    "justify",
    "float",
    "clear",
    "overflow",
)
_COLORS = ("color", "background", "fill", "stroke", "opacity")
_BOX = ("margin", "padding", "border", "box-", "outline")


class CssElementPanel(QWidget):
    """Prezentuje raport CSSOM, filtry, preview i bezpieczne akcje źródłowe."""

    def __init__(
        self,
        *,
        source_text: Callable[[RuleIdentity], str | None],
        revision_matches: Callable[[RuleIdentity], bool],
        preview_rule: Callable[[str, str, bool], None],
        apply_rule: Callable[[RuleIdentity, str], bool],
        jump_rule: Callable[[RuleIdentity], None],
        show_element_source: Callable[[str], None],
        create_rule: Callable[[str, str | None], None],
        highlight_matches: Callable[[str], None],
    ) -> None:
        super().__init__()
        self._source_text = source_text
        self._revision_matches = revision_matches
        self._preview_rule = preview_rule
        self._apply_rule = apply_rule
        self._jump_rule = jump_rule
        self._show_element_source = show_element_source
        self._create_rule = create_rule
        self._highlight_matches = highlight_matches
        self._inspection = ElementInspection(False)
        self._selected_rule: InspectorRule | None = None
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._preview_edit)
        self.rule_editor.editor.textChanged.connect(self._timer.start)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.breadcrumb_label = QLabel()
        self.breadcrumb_label.setWordWrap(True)
        self.element_label = QLabel()
        self.element_label.setWordWrap(True)
        self.box_label = QLabel()
        self.box_label.setWordWrap(True)
        self.font_label = QLabel()
        self.font_label.setWordWrap(True)
        for widget_label in (
            self.breadcrumb_label,
            self.element_label,
            self.box_label,
            self.font_label,
        ):
            layout.addWidget(widget_label)

        filters = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(_("Szukaj właściwości…"))
        self.search_edit.setToolTip(_("Filtruj deklaracje po nazwie właściwości"))
        self.search_edit.textChanged.connect(self._rebuild_tree)
        filters.addWidget(self.search_edit, stretch=1)
        self.filter_checks: dict[str, QCheckBox] = {}
        for key, filter_label in (
            ("typography", _("Typografia")),
            ("layout", _("Layout")),
            ("colors", _("Kolory")),
            ("box", _("Box model")),
            ("overridden", _("Nadpisane")),
        ):
            check = QCheckBox(filter_label)
            check.setToolTip(_("Włącz filtr: {name}").format(name=filter_label))
            check.toggled.connect(self._rebuild_tree)
            filters.addWidget(check)
            self.filter_checks[key] = check
        layout.addLayout(filters)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(
            [_("Właściwość / reguła"), _("Zadeklarowana"), _("Computed"), _("Stan"), _("Źródło")]
        )
        self.tree.currentItemChanged.connect(self._on_selection)
        splitter.addWidget(self.tree)
        self.rule_editor = CodeEditor()
        self.rule_editor.read_only = True
        splitter.addWidget(self.rule_editor)
        splitter.setSizes([360, 150])
        layout.addWidget(splitter, stretch=1)

        scope_row = QHBoxLayout()
        self.scope_combo = QComboBox()
        self.scope_combo.setToolTip(_("Zakres tymczasowej warstwy CSS"))
        self.scope_combo.addItem(_("Bieżący element"), "current")
        self.scope_combo.addItem(_("Wszystkie dopasowania"), "all")
        self.scope_combo.addItem(_("Reprezentatywne rozdziały — później"), "chapters")
        self.scope_combo.currentIndexChanged.connect(self._timer_start_if_editable)
        item = cast(QStandardItemModel, self.scope_combo.model()).item(2)
        if item is not None:
            item.setEnabled(False)
        scope_row.addWidget(self.scope_combo)
        self.preview_status = QLabel()
        self.preview_status.setWordWrap(True)
        scope_row.addWidget(self.preview_status, stretch=1)
        layout.addLayout(scope_row)

        actions = QHBoxLayout()
        self.jump_button = self._button(_("Przejdź do reguły"), self._jump)
        self.source_button = self._button(_("Pokaż źródło elementu"), self._show_source)
        self.create_button = self._button(_("Utwórz regułę dla elementu"), self._create)
        self.copy_button = self._button(_("Kopiuj selektor"), self._copy_selector)
        self.highlight_button = self._button(_("Podświetl wszystkie dopasowania"), self._highlight)
        self.apply_button = self._button(_("Zastosuj"), self._apply)
        for button in (
            self.jump_button,
            self.source_button,
            self.create_button,
            self.copy_button,
            self.highlight_button,
            self.apply_button,
        ):
            actions.addWidget(button)
        layout.addLayout(actions)

        self.limitations_label = QLabel()
        self.limitations_label.setWordWrap(True)
        layout.addWidget(self.limitations_label)

    def _button(self, text: str, slot: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.setToolTip(text)
        button.clicked.connect(slot)
        return button

    def set_inspection(self, inspection: ElementInspection) -> None:
        """Podmienia raport i zachowuje wszystkie jawne ograniczenia."""
        self._inspection = inspection
        element = inspection.element
        if not inspection.available or element is None:
            self.breadcrumb_label.setText(
                inspection.error or _("Wybierz element w dokładnym podglądzie.")
            )
            self.element_label.clear()
            self.box_label.clear()
            self.font_label.clear()
        else:
            self.breadcrumb_label.setText(
                _("DOM: {path}").format(path=" > ".join(element.breadcrumb))
            )
            classes = " ".join(element.classes)
            self.element_label.setText(
                _("Element: {tag}  id={id}  klasy={classes}\n{text}").format(
                    tag=element.tag,
                    id=element.element_id or "—",
                    classes=classes or "—",
                    text=element.text,
                )
            )
            self.box_label.setText(_format_box(inspection.box))
            self.font_label.setText(_format_font(inspection))
        self.limitations_label.setText(
            _("Ograniczenia: {items}").format(items=" ".join(inspection.limitations))
            if inspection.limitations
            else ""
        )
        self._rebuild_tree()

    def set_preview_result(self, result: object) -> None:
        """Pokazuje wynik asynchronicznej walidacji warstwy preview."""
        if not isinstance(result, dict):
            return
        if result.get("ok"):
            self.preview_status.setText(
                _(
                    "Preview: {count} dopasowań. Uwaga: warstwa na końcu dokumentu może mieć inną kolejność niż źródło."
                ).format(count=result.get("matches", 0))
            )
        else:
            self.preview_status.setText(
                _("Błąd preview: {error} — zachowano ostatnią poprawną warstwę.").format(
                    error=result.get("error", "CSS")
                )
            )

    def _rebuild_tree(self) -> None:
        selected_identity = self._selected_rule.identity if self._selected_rule else None
        self.tree.clear()
        query = self.search_edit.text().strip().lower()
        for rule in self._inspection.rules:
            declarations = [
                decl
                for decl in rule.declarations
                if self._visible(decl.property, decl.state, query)
            ]
            if not declarations:
                continue
            context = " / ".join(rule.contexts)
            source = rule.stylesheet_path or _("inline")
            if rule.source_line is not None:
                source += f":{rule.source_line}:{rule.source_column or 1}"
            title = f"{rule.selector}  [{context}]" if context else rule.selector
            parent = QTreeWidgetItem(
                [title, "", "", _("aktywna") if rule.active else _("nieaktywna"), source]
            )
            parent.setData(0, _RULE_ROLE, rule)
            self.tree.addTopLevelItem(parent)
            for decl in declarations:
                important = " !important" if decl.important else ""
                child = QTreeWidgetItem(
                    [
                        decl.property,
                        decl.declared + important,
                        decl.computed,
                        _state_label(decl.state),
                        _declaration_source(rule, decl.winner_order, decl.state),
                    ]
                )
                child.setData(0, _RULE_ROLE, rule)
                parent.addChild(child)
            parent.setExpanded(True)
            if selected_identity is not None and rule.identity == selected_identity:
                self.tree.setCurrentItem(parent)
        inherited_items = [
            item
            for item in self._inspection.inherited
            if self._visible(str(item.get("property", "")), "winning", query)
        ]
        if inherited_items:
            inherited_parent = QTreeWidgetItem(
                [_("Właściwości dziedziczone"), "", "", _("dziedziczona"), ""]
            )
            self.tree.addTopLevelItem(inherited_parent)
            for inherited in inherited_items:
                inherited_parent.addChild(
                    QTreeWidgetItem(
                        [
                            str(inherited.get("property", "")),
                            "",
                            str(inherited.get("computed", "")),
                            _("dziedziczona"),
                            str(inherited.get("from", "")),
                        ]
                    )
                )
            inherited_parent.setExpanded(True)
        if self.tree.currentItem() is None and self.tree.topLevelItemCount():
            first = self.tree.topLevelItem(0)
            if first is not None:
                self.tree.setCurrentItem(first)

    def _visible(self, prop: str, state: str, query: str) -> bool:
        low = prop.lower()
        if query and query not in low:
            return False
        if self.filter_checks["overridden"].isChecked() and state == "winning":
            return False
        categories = [
            key
            for key in ("typography", "layout", "colors", "box")
            if self.filter_checks[key].isChecked()
        ]
        if not categories:
            return True
        prefixes = {"typography": _TYPOGRAPHY, "layout": _LAYOUT, "colors": _COLORS, "box": _BOX}
        return any(low.startswith(prefixes[key]) for key in categories)

    def _on_selection(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        rule = current.data(0, _RULE_ROLE) if current is not None else None
        if not isinstance(rule, InspectorRule):
            return
        self._selected_rule = rule
        text = self._source_text(rule.identity) if rule.identity is not None else None
        self.rule_editor.read_only = rule.identity is None
        self.rule_editor.editor.blockSignals(True)
        self.rule_editor.load(
            text or _("/* Reguła tylko do odczytu: brak wiarygodnego spanu źródła. */"), "css"
        )
        self.rule_editor.editor.blockSignals(False)
        editable = rule.identity is not None
        self.jump_button.setEnabled(editable)
        self.apply_button.setEnabled(editable)

    def _preview_edit(self) -> None:
        rule = self._selected_rule
        if rule is None or rule.identity is None:
            return
        text = self.rule_editor.get_text()
        if isinstance(parse_single_rule(text), list):
            self.preview_status.setText(_("Błąd CSS — zachowano ostatnią poprawną warstwę."))
            return
        self._preview_rule(rule.selector, text, self.scope_combo.currentData() == "current")

    def _timer_start_if_editable(self) -> None:
        """Ponawia preview po zmianie zakresu tylko dla edytowalnej reguły."""
        if self._selected_rule is not None and self._selected_rule.identity is not None:
            self._timer.start()

    def _apply(self) -> None:
        rule = self._selected_rule
        if rule is None or rule.identity is None:
            return
        if not self._revision_matches(rule.identity):
            self.preview_status.setText(
                _("Konflikt revision: źródło zmieniło się. Niczego nie nadpisano.")
            )
            return
        text = self.rule_editor.get_text()
        if isinstance(parse_single_rule(text), list):
            return
        if self._apply_rule(rule.identity, text):
            self.preview_status.setText(_("Zastosowano jako jedną operację Undo."))
        else:
            self.preview_status.setText(
                _("Nie zastosowano zmiany. Sprawdź tryb edycji i aktualność źródła.")
            )

    def _jump(self) -> None:
        if self._selected_rule and self._selected_rule.identity:
            self._jump_rule(self._selected_rule.identity)

    def _show_source(self) -> None:
        element = self._inspection.element
        if element and element.node_id:
            self._show_element_source(element.node_id)

    def _selector(self) -> str:
        rule = self._selected_rule
        if rule is not None:
            return rule.selector
        element = self._inspection.element
        if element is None:
            return ""
        if element.element_id:
            return f"#{element.element_id}"
        return element.tag + "".join(f".{name}" for name in element.classes)

    def _create(self) -> None:
        element = self._inspection.element
        selector = ""
        if element is not None:
            selector = (
                f"#{element.element_id}"
                if element.element_id
                else element.tag + "".join(f".{name}" for name in element.classes)
            )
        preferred = next(
            (rule.stylesheet_path for rule in self._inspection.rules if rule.stylesheet_path), None
        )
        if selector:
            self._create_rule(selector, preferred)

    def _copy_selector(self) -> None:
        selector = self._selector()
        if selector:
            QApplication.clipboard().setText(selector)

    def _highlight(self) -> None:
        selector = self._selector()
        if selector:
            self._highlight_matches(selector)


def _format_box(box: object) -> str:
    if not isinstance(box, dict):
        return ""

    def values(name: str) -> str:
        item = box.get(name, {})
        return (
            "/".join(str(item.get(side, "")) for side in ("top", "right", "bottom", "left"))
            if isinstance(item, dict)
            else ""
        )

    content = box.get("content", {})
    size = (
        f"{content.get('width', '')} x {content.get('height', '')}"
        if isinstance(content, dict)
        else ""
    )
    return _(
        "Box: margin {margin} · border {border} · padding {padding} · content {content}"
    ).format(
        margin=values("margin"), border=values("border"), padding=values("padding"), content=size
    )


def _format_font(inspection: ElementInspection) -> str:
    font = inspection.font
    if font is None:
        return ""
    return _(
        "Font: {used} · computed {computed} · osadzony {embedded} ({status}) · fallback {fallback}"
    ).format(
        used=font.used_family,
        computed=font.computed_family,
        embedded=_("tak") if font.embedded else _("nie"),
        status=font.status,
        fallback=", ".join(font.fallbacks) or "—",
    )


def _state_label(state: str) -> str:
    return {
        "winning": _("zwycięska"),
        "partial": _("częściowo nadpisana"),
        "lost": _("przegrana"),
        "inactive": _("nieaktywna"),
    }.get(state, state)


def _declaration_source(rule: InspectorRule, winner_order: int | None, state: str) -> str:
    """Pokazuje kolejność/specyficzność i wskazuje zwycięzcę przegranej deklaracji."""
    winner = f" -> {_('wygrywa')} #{winner_order}" if state == "lost" and winner_order else ""
    return f"spec={rule.specificity} · #{rule.order}{winner}"
