"""Testy GUI inspektora CSS (CssInspector + integracja w EditorTab)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

import epubforge.gui.widgets.css_inspector as inspector_module
from epubforge.fixers.css_rules import CssDecl, CssRuleInfo, parse_rules
from epubforge.gui.css_inspection import InspectorRule, RuleIdentity, content_revision
from epubforge.gui.css_inspector_limits import MAX_CSS_INSPECTOR_SOURCE_BYTES
from epubforge.gui.preview.backend import BackendKind
from epubforge.gui.preview.webengine_backend import _decode_json_object
from epubforge.gui.tabs.editor import EditorTab
from epubforge.gui.widgets.css_inspector import CssInspector
from epubforge.gui.widgets.css_sheet_format import declaration_shortcut

pytestmark = pytest.mark.gui

_CSS = "h1 { color: red }\np { font-size: 12pt; letter-spacing: 2px }\n"


def _many_rules(count: int) -> str:
    """Buduje mały syntetyczny arkusz bez dużego fixture w repo."""
    return "\n".join(f".rule-{index} {{ color: red }}" for index in range(count))


def _element_report(count: int) -> dict[str, object]:
    """Buduje raport CSSOM możliwy do mapowania bez uruchamiania Chromium."""
    return {
        "available": True,
        "element": {"tag": "p", "id": "target", "classes": [], "text": "x"},
        "rules": [
            {
                "selector": f".rule-{index}",
                "stylesheet_path": "OEBPS/s.css",
                "rule_path": [index],
                "active": True,
                "matched": True,
                "specificity": [0, 1, 0],
                "order": index,
                "declarations": [
                    {
                        "property": "special-color" if index % 10 == 0 else "color",
                        "declared": "red",
                        "computed": "rgb(255, 0, 0)",
                        "state": "winning",
                        "winner_order": index,
                    }
                ],
            }
            for index in range(count)
        ],
    }


def test_webengine_json_transport_decodes_objects() -> None:
    """Złożone wyniki Chromium są dekodowane ze stabilnego transportu JSON."""
    assert _decode_json_object('{"ok":true,"matches":1}') == {"ok": True, "matches": 1}
    with pytest.raises(ValueError, match="nie jest obiektem"):
        _decode_json_object("[]")


def _make_css_epub(path: Path, css: str = _CSS) -> None:
    container = (
        b'<?xml version="1.0"?><container version="1.0" '
        b'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        b'<rootfiles><rootfile full-path="OEBPS/content.opf" '
        b'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        b'<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" '
        b'version="3.0" unique-identifier="i">'
        b'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        b'<dc:identifier id="i">x</dc:identifier><dc:title>T</dc:title></metadata>'
        b'<manifest><item id="c" href="s.css" media-type="text/css"/>'
        b'<item id="h" href="a.xhtml" media-type="application/xhtml+xml"/></manifest>'
        b'<spine><itemref idref="h"/></spine></package>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/s.css", css.encode("utf-8"))
        zf.writestr("OEBPS/a.xhtml", b"<html><body><p>x</p></body></html>")


def _open_css(qtbot: QtBot, tmp_path: Path, css: str = _CSS) -> EditorTab:
    book = tmp_path / "b.epub"
    _make_css_epub(book, css)
    tab = EditorTab()
    qtbot.addWidget(tab)
    tab.open_epub(book)
    tab.edit_toggle.setChecked(True)
    tab._select_path("OEBPS/s.css")
    return tab


def test_inspector_visible_for_css_and_loads_rule(qtbot: QtBot, tmp_path: Path) -> None:
    """Dla CSS panel jest aktywny i wybór reguły ładuje edytor reguły."""
    tab = _open_css(qtbot, tmp_path)
    assert tab.inspector_toggle.isEnabled()
    assert not tab.css_inspector.isHidden()
    insp = tab.css_inspector
    insp.tree.setCurrentItem(insp.tree.topLevelItem(0))
    assert insp.rule_editor.get_text().strip() == "h1 { color: red }"


def test_inspector_hidden_for_non_css(qtbot: QtBot, tmp_path: Path) -> None:
    """Dla pliku nie-CSS panel jest schowany i toggle nieaktywny."""
    tab = _open_css(qtbot, tmp_path)
    tab._select_path("OEBPS/a.xhtml")
    assert tab.css_inspector.isHidden()
    assert not tab.inspector_toggle.isEnabled()
    assert "WebEngine" in tab.inspector_toggle.toolTip()


def test_exact_html_enables_element_inspector_without_view_toggle(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Zwykły XHTML jest kwalifikowany od razu, bez kliknięcia Kod/Podgląd/Podział."""
    tab = _open_css(qtbot, tmp_path)
    tab._select_path("OEBPS/a.xhtml")
    tab.book_preview._active.kind = BackendKind.WEBENGINE
    tab.book_preview._ready_document = "OEBPS/a.xhtml"

    tab._update_inspector()

    assert tab.inspector_toggle.isEnabled()
    assert not tab.css_inspector.isHidden()
    assert tab.css_inspector.mode_tabs.isTabEnabled(1)
    assert tab.css_inspector.mode_tabs.currentIndex() == 1


def test_live_preview_updates_after_debounce(qtbot: QtBot, tmp_path: Path) -> None:
    """Edycja color: red → blue po debounce zmienia podgląd (Qt: blue → #0000ff)."""
    tab = _open_css(qtbot, tmp_path)
    insp = tab.css_inspector
    insp.tree.setCurrentItem(insp.tree.topLevelItem(0))
    insp.rule_editor.editor.setPlainText("h1 { color: blue }")
    qtbot.wait(400)  # przeskocz debounce 300 ms
    assert "#0000ff" in insp.preview.toHtml().lower()


def test_apply_writes_to_main_editor_and_undo_reverts(qtbot: QtBot, tmp_path: Path) -> None:
    """Zastosuj wpisuje zmianę do głównego edytora; undo cofa ją w całości."""
    tab = _open_css(qtbot, tmp_path)
    insp = tab.css_inspector
    insp.tree.setCurrentItem(insp.tree.topLevelItem(0))
    insp.rule_editor.editor.setPlainText("h1 { color: blue }")
    insp.apply_button.click()

    assert "color: blue" in tab.code_editor.get_text()
    qtbot.keyClick(tab.code_editor.editor, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert "color: red" in tab.code_editor.get_text()
    assert "color: blue" not in tab.code_editor.get_text()


def test_read_only_inspector_hides_apply(qtbot: QtBot) -> None:
    """Inspektor bez apply_replacement (np. podgląd presetu) chowa Zastosuj."""
    inspector = CssInspector(get_source=lambda: _CSS, apply_replacement=None)
    qtbot.addWidget(inspector)
    assert not inspector.apply_button.isVisibleTo(inspector)
    assert inspector.rule_editor.read_only is True
    assert inspector.tree.topLevelItemCount() == 2


def test_sheet_rule_tree_materializes_only_first_page(qtbot: QtBot) -> None:
    """Duży model nie tworzy od razu itemu Qt dla każdej reguły."""
    inspector = CssInspector(get_source=lambda: _many_rules(1200))
    qtbot.addWidget(inspector)

    assert inspector.tree.topLevelItemCount() == inspector.RULE_PAGE_SIZE
    assert inspector.show_more_button.isEnabled()


def test_sheet_show_more_uses_existing_model_without_duplicates(qtbot: QtBot) -> None:
    """Kolejne strony dokładają stabilne globalne indeksy bez ponownego parsowania."""
    source_calls = 0

    def source() -> str:
        nonlocal source_calls
        source_calls += 1
        return _many_rules(1200)

    inspector = CssInspector(get_source=source)
    qtbot.addWidget(inspector)
    calls_after_refresh = source_calls

    inspector.show_more_button.click()
    inspector.show_more_button.click()

    assert inspector.tree.topLevelItemCount() == 1200
    indexes = [
        inspector.tree.topLevelItem(index).data(0, Qt.ItemDataRole.UserRole)
        for index in range(inspector.tree.topLevelItemCount())
    ]
    assert indexes == list(range(1200))
    assert source_calls == calls_after_refresh
    assert not inspector.show_more_button.isEnabled()


def test_new_and_empty_sheet_reset_rule_pagination(qtbot: QtBot) -> None:
    """Nowe źródło oraz pusty arkusz nie dziedziczą odsłoniętych stron."""
    state = {"source": _many_rules(1200)}
    inspector = CssInspector(get_source=lambda: state["source"])
    qtbot.addWidget(inspector)
    inspector.show_more_button.click()
    assert inspector.tree.topLevelItemCount() == 2 * inspector.RULE_PAGE_SIZE

    state["source"] = _many_rules(100)
    inspector.refresh()
    assert inspector.tree.topLevelItemCount() == 100
    assert not inspector.show_more_button.isEnabled()

    state["source"] = ""
    inspector.refresh()
    assert inspector.tree.topLevelItemCount() == 0
    assert inspector._rules == []
    assert not inspector.show_more_button.isEnabled()


def test_sheet_model_exact_limit_is_complete(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Dokładnie inspector limit reguł nie pokazuje fałszywego truncation."""
    monkeypatch.setattr(inspector_module, "MAX_CSS_INSPECTOR_RULES", 3)
    inspector = CssInspector(get_source=lambda: _many_rules(3))
    qtbot.addWidget(inspector)
    assert len(inspector._rules) == 3
    assert inspector.limit_label.text() == ""


def test_sheet_model_limit_plus_one_is_bounded_and_reported(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Limit+1 pozostawia źródło nietknięte i jawnie ogranicza wyłącznie inspector."""
    source = _many_rules(4)
    monkeypatch.setattr(inspector_module, "MAX_CSS_INSPECTOR_RULES", 3)
    inspector = CssInspector(get_source=lambda: source)
    qtbot.addWidget(inspector)
    assert len(inspector._rules) == 3
    assert "ograniczył" in inspector.limit_label.text()
    assert source.endswith(".rule-3 { color: red }")


def test_sheet_declaration_shortcut_stops_after_visible_prefix() -> None:
    """Jedna reguła z wieloma deklaracjami nie buduje pełnego pomocniczego stringa."""

    class GuardedDeclarations(list[CssDecl]):
        def __iter__(self):  # type: ignore[no-untyped-def]
            for index, declaration in enumerate(super().__iter__()):
                if index >= 10:
                    raise AssertionError("skrót nie może iterować po całej dużej regule")
                yield declaration

    declarations = GuardedDeclarations(
        CssDecl(f"very-long-property-{index}", "very-long-value") for index in range(1000)
    )
    rule = CssRuleInfo("a", declarations, (0, 1))
    shortcut = declaration_shortcut(rule)
    assert len(shortcut) <= 60
    assert shortcut.endswith("…")


def test_oversized_sheet_is_unavailable_without_parsing(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inspector-specific byte cap nie obniża validity ani nie uruchamia parsera."""
    source = _many_rules(20)
    monkeypatch.setattr(inspector_module, "MAX_CSS_INSPECTOR_SOURCE_BYTES", 32)
    monkeypatch.setattr(
        inspector_module,
        "parse_rules_bounded",
        lambda *_args, **_kwargs: pytest.fail("oversized source nie może wejść do parsera"),
    )
    inspector = CssInspector(get_source=lambda: source)
    qtbot.addWidget(inspector)
    assert inspector._rules == []
    assert "zbyt duży" in inspector.limit_label.text()
    assert source == _many_rules(20)


def test_sheet_source_exact_byte_limit_is_inspectable(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dokładnie source byte cap uruchamia parser i zachowuje pełny model."""
    source = ".x { color: red }"
    monkeypatch.setattr(inspector_module, "MAX_CSS_INSPECTOR_SOURCE_BYTES", len(source))
    inspector = CssInspector(get_source=lambda: source)
    qtbot.addWidget(inspector)
    assert len(inspector._rules) == 1
    assert "zbyt duży" not in inspector.limit_label.text()


def test_element_source_provider_checks_archive_size_before_read(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Niezmieniony duży CSS jest odrzucony z metadanych przed dekompresją ZIP."""
    tab = _open_css(qtbot, tmp_path)
    tab._select_path("OEBPS/a.xhtml")
    assert tab._epub is not None
    monkeypatch.setattr(
        tab._epub, "get_file_size", lambda _path: MAX_CSS_INSPECTOR_SOURCE_BYTES + 1
    )
    monkeypatch.setattr(
        tab._epub,
        "read_file",
        lambda _path: pytest.fail("oversized CSS nie może zostać odczytany"),
    )

    assert tab._css_source_snapshot("OEBPS/s.css") is None


def test_css_source_snapshot_prefers_current_then_dirty_then_archive(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Snapshot mapowania nie może pominąć nowszego edytora ani dirty overlay."""
    tab = _open_css(qtbot, tmp_path)
    tab._dirty["OEBPS/s.css"] = "dirty { color: blue }"
    tab.code_editor.editor.setPlainText("current { color: green }")
    current = tab._css_source_snapshot("OEBPS/s.css")
    assert current is not None and current[0] == "current { color: green }"

    tab._select_path("OEBPS/a.xhtml")
    tab._dirty["OEBPS/s.css"] = "dirty { color: blue }"
    dirty = tab._css_source_snapshot("OEBPS/s.css")
    assert dirty is not None and dirty[0] == "dirty { color: blue }"


def test_element_tree_materializes_pages_without_duplicates(qtbot: QtBot) -> None:
    """Tryb Element ogranicza rodziców i deklaracje Qt do odsłoniętych stron."""
    source = _many_rules(600)
    inspector = CssInspector(
        get_source=lambda: "",
        source_provider=lambda _path: (source, content_revision(source)),
    )
    qtbot.addWidget(inspector)

    inspector.set_element_report(_element_report(600))
    panel = inspector.element_panel
    assert panel.tree.topLevelItemCount() == panel.RULE_PAGE_SIZE
    assert panel.show_more_button.isEnabled()

    panel.show_more_button.click()
    panel.show_more_button.click()

    rules = [
        panel.tree.topLevelItem(index).data(0, Qt.ItemDataRole.UserRole)
        for index in range(panel.tree.topLevelItemCount())
    ]
    assert all(isinstance(rule, InspectorRule) for rule in rules)
    assert [rule.order for rule in rules if isinstance(rule, InspectorRule)] == list(range(600))
    assert not panel.show_more_button.isEnabled()


def test_element_filter_and_new_report_reset_pagination(qtbot: QtBot) -> None:
    """Filtr oraz nowy raport zaczynają od pierwszej strony nowego widoku."""
    source = _many_rules(600)
    inspector = CssInspector(
        get_source=lambda: "",
        source_provider=lambda _path: (source, content_revision(source)),
    )
    qtbot.addWidget(inspector)
    inspector.set_element_report(_element_report(600))
    panel = inspector.element_panel
    panel.show_more_button.click()
    assert panel.tree.topLevelItemCount() == 2 * panel.RULE_PAGE_SIZE

    panel.search_edit.setText("special")
    assert panel.tree.topLevelItemCount() == 60
    assert not panel.show_more_button.isEnabled()

    panel.search_edit.clear()
    inspector.set_element_report(_element_report(100))
    assert panel.tree.topLevelItemCount() == 100
    assert not panel.show_more_button.isEnabled()


def test_empty_element_report_clears_later_page_rule_identity(qtbot: QtBot) -> None:
    """Pusty nowy raport nie zostawia akcji wskazujących regułę z późniejszej strony."""
    source = _many_rules(600)
    jumped: list[RuleIdentity] = []
    applied: list[RuleIdentity] = []
    previewed: list[str] = []
    inspector = CssInspector(
        get_source=lambda: "",
        source_provider=lambda _path: (source, content_revision(source)),
        jump_rule=jumped.append,
        apply_mapped_rule=lambda identity, _text: not applied.append(identity),
        preview_rule=lambda selector, _text, _current: previewed.append(selector),
    )
    qtbot.addWidget(inspector)
    inspector.set_element_report(_element_report(600))
    panel = inspector.element_panel
    panel.show_more_button.click()
    later = panel.tree.topLevelItem(panel.RULE_PAGE_SIZE + 10)
    panel.tree.setCurrentItem(later)
    assert panel._selected_rule is not None
    panel.jump_button.click()
    panel.apply_button.click()
    panel._preview_edit()
    assert jumped[0].rule_path == (210,)
    assert applied[0] == jumped[0]
    assert previewed == [".rule-210"]

    inspector.set_element_report(_element_report(0))

    assert panel._selected_rule is None
    assert panel.rule_editor.get_text() == ""
    assert not panel.jump_button.isEnabled()
    assert not panel.apply_button.isEnabled()


def test_sheet_revision_conflict_does_not_overwrite(qtbot: QtBot) -> None:
    """Zastosuj nie używa starego spanu po zewnętrznej zmianie źródła."""
    state = {"source": _CSS}
    calls: list[tuple[int, int, str]] = []
    inspector = CssInspector(
        get_source=lambda: state["source"],
        apply_replacement=lambda start, end, text: calls.append((start, end, text)),
    )
    qtbot.addWidget(inspector)
    inspector.tree.setCurrentItem(inspector.tree.topLevelItem(0))
    inspector.rule_editor.editor.setPlainText("h1 { color: blue }")
    state["source"] = "/* nowsza treść */\n" + _CSS
    inspector.apply_button.click()
    assert calls == []
    assert "Konflikt revision" in inspector.error_label.text()


def test_jump_to_rule_uses_path_and_span_for_duplicate_selector(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Przejście wybiera drugie wystąpienie selektora, a nie pierwszy tekst o tej nazwie."""
    css = "p { color: red }\n@media screen { p { color: blue } }\n"
    tab = _open_css(qtbot, tmp_path, css)
    second = parse_rules(css)[1]
    identity = RuleIdentity(
        "OEBPS/s.css",
        second.rule_path,
        second.span,
        generation=4,
        revision=content_revision(css),
    )
    tab._jump_to_css_rule(identity)
    assert tab.code_editor.editor.textCursor().selectedText() == "p { color: blue }"
