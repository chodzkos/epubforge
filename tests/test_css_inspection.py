"""Testy mapowania raportu Chromium na dokładne reguły i rewizje źródła."""

from __future__ import annotations

from epubforge.gui.css_inspection import content_revision, map_element_report, source_snapshot
from epubforge.gui.preview.css_bridge import INSPECT_SCRIPT
from epubforge.gui.resource_limits import (
    MAX_CSS_ELEMENT_REPORT_LIMITATIONS,
    MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS,
    MAX_CSS_ELEMENT_REPORT_PATH_DEPTH,
    MAX_CSS_ELEMENT_REPORT_TEXT_CHARS,
)


def _report(path: tuple[int, ...], *, active: bool = True) -> dict[str, object]:
    return {
        "available": True,
        "node_id": "n1",
        "breadcrumb": ["html", "body", "p.x"],
        "element": {"tag": "p", "id": "", "classes": ["x"], "text": "Akapit"},
        "box": {},
        "font": {"used_family": "Book", "computed_family": "Book, serif"},
        "inherited": [{"property": "color", "computed": "rgb(0, 0, 0)", "from": "body"}],
        "limitations": [],
        "rules": [
            {
                "selector": ".x",
                "stylesheet_path": "OEBPS/book.css",
                "rule_path": list(path),
                "contexts": [{"type": "media", "condition": "screen"}],
                "active": active,
                "matched": True,
                "specificity": [0, 1, 0],
                "order": 7,
                "declarations": [
                    {
                        "property": "color",
                        "declared": "red",
                        "computed": "rgb(255, 0, 0)",
                        "important": False,
                        "state": "winning" if active else "inactive",
                        "winner_order": 7,
                    }
                ],
            }
        ],
    }


def test_same_selector_maps_by_rule_path_not_selector() -> None:
    """Duplikat selektora w @media mapuje się na drugie, konkretne wystąpienie."""
    source = ".x { color: blue }\n@media screen { .x { color: red } }\n"
    revision = content_revision(source)
    inspection = map_element_report(
        _report((1, 0)),
        lambda path: (source, revision) if path == "OEBPS/book.css" else None,
        generation=12,
    )
    rule = inspection.rules[0]
    assert rule.identity is not None
    assert source[slice(*rule.identity.span)] == ".x { color: red }"
    assert rule.identity.rule_path == (1, 0)
    assert rule.identity.generation == 12
    assert rule.identity.revision == revision


def test_inactive_media_is_visible_and_mapped() -> None:
    """Nieaktywne @media nie znika i zachowuje stan deklaracji."""
    source = "@media print { .x { color: red } }"
    inspection = map_element_report(
        _report((0, 0), active=False),
        lambda _path: source_snapshot(source),
        generation=2,
    )
    assert inspection.rules[0].active is False
    assert inspection.rules[0].declarations[0].state == "inactive"
    assert inspection.rules[0].contexts == ("@media screen",)


def test_unmapped_rule_is_reported_not_dropped() -> None:
    """Rozjazd CSSOM/parser pozostaje w raporcie i daje jawne ograniczenie."""
    inspection = map_element_report(
        _report((8, 4)),
        lambda _path: source_snapshot(".x { color: red }"),
        generation=1,
    )
    assert len(inspection.rules) == 1
    assert inspection.rules[0].source_mapped is False
    assert any("Nie zmapowano" in item for item in inspection.limitations)


def test_content_revision_changes_with_exact_source() -> None:
    """Kontrola konfliktu reaguje nawet na zmianę formatowania poza regułą."""
    assert content_revision("p{color:red}") != content_revision("p { color:red }")


def test_reader_overrides_and_limitations_are_visible_in_inspector() -> None:
    report = _report((0,))
    report["reader_simulation"] = {
        "overrides": {"rozmiar tekstu": "22px", "CSS wydawcy": "wyłączony"},
        "limitations": ["Typografia fixed-layout została pominięta."],
    }
    inspection = map_element_report(
        report, lambda _path: source_snapshot(".x { color: red }"), generation=3
    )
    assert inspection.reader_simulation["overrides"]["rozmiar tekstu"] == "22px"
    assert any("Symulator:" in item for item in inspection.limitations)


def test_element_report_accepts_exact_rule_limit() -> None:
    """Dokładnie limit reguł raportu pozostaje dostępny i nieoznaczony jako ucięty."""
    report = _report((0,))
    report["rules"] = report["rules"] * 3
    inspection = map_element_report(
        report,
        lambda _path: source_snapshot(".x { color: red }"),
        generation=3,
        max_rules=3,
        max_declarations=3,
    )
    assert len(inspection.rules) == 3
    assert inspection.truncated is False


def test_element_report_limit_plus_one_is_bounded_and_reported() -> None:
    """Raport limit+1 tworzy bounded model i jawne ograniczenie UX."""
    report = _report((0,))
    report["rules"] = report["rules"] * 4
    inspection = map_element_report(
        report,
        lambda _path: source_snapshot(".x { color: red }"),
        generation=3,
        max_rules=3,
        max_declarations=10,
    )
    assert inspection.rules == ()
    assert inspection.truncated is True
    assert any("ograniczył" in item for item in inspection.limitations)


def test_element_report_python_cap_never_exposes_partial_cascade_identities() -> None:
    """Niezależny cap Pythona usuwa akcje, bo pominięta reguła może zmienić winnera."""
    report = _report((0,))
    rules = report["rules"]
    assert isinstance(rules, list)
    report["rules"] = rules * 2
    inspection = map_element_report(
        report,
        lambda _path: source_snapshot(".x { color: red }"),
        generation=3,
        max_rules=1,
        max_declarations=10,
    )
    assert inspection.truncated is True
    assert inspection.rules == ()


def test_malformed_rule_path_is_non_actionable() -> None:
    """Odrzucenie składnika ścieżki nie może przypadkiem zmapować innej reguły."""
    report = _report((0,))
    rules = report["rules"]
    assert isinstance(rules, list) and isinstance(rules[0], dict)
    rules[0]["rule_path"] = [0, "invalid"]
    source_calls = 0

    def source_provider(_path: str):  # type: ignore[no-untyped-def]
        nonlocal source_calls
        source_calls += 1
        return source_snapshot(".x { color: red }")

    inspection = map_element_report(report, source_provider, generation=3)
    assert source_calls == 0
    assert inspection.rules[0].identity is None
    assert inspection.truncated is True


def test_webengine_truncation_flag_is_preserved() -> None:
    """Bounded raport Chromium nie traci jawnej informacji podczas mapowania."""
    report = _report((0,))
    report["truncated"] = True
    inspection = map_element_report(
        report, lambda _path: source_snapshot(".x { color: red }"), generation=4
    )
    assert inspection.truncated is True
    assert any("ograniczył" in item for item in inspection.limitations)


def test_element_declaration_limit_stops_before_materializing_raw_list() -> None:
    """Nieufna reguła limit+1 nie jest kopiowana w całości przed kontrolą budżetu."""

    class GuardedDeclarations(list[dict[str, object]]):
        def __iter__(self):  # type: ignore[no-untyped-def]
            for index, declaration in enumerate(super().__iter__()):
                if index > 3:
                    raise AssertionError("mapper nie może przejść poza limit+1")
                yield declaration

    report = _report((0,))
    rules = report["rules"]
    assert isinstance(rules, list) and isinstance(rules[0], dict)
    declarations = rules[0]["declarations"]
    assert isinstance(declarations, list) and isinstance(declarations[0], dict)
    rules[0]["declarations"] = GuardedDeclarations([declarations[0]] * 100)
    inspection = map_element_report(
        report,
        lambda _path: source_snapshot(".x { color: red }"),
        generation=4,
        max_rules=10,
        max_declarations=3,
    )
    assert inspection.rules == ()
    assert inspection.truncated is True


def test_element_declaration_cardinality_rejects_before_iteration() -> None:
    """Znany rozmiar listy limit+1 odrzuca rekord przed iteracją nieufnych elementów."""

    class NeverIterate(list[dict[str, object]]):
        def __iter__(self):  # type: ignore[no-untyped-def]
            raise AssertionError("cardinality cap musi poprzedzać iterację")

    report = _report((0,))
    rules = report["rules"]
    assert isinstance(rules, list) and isinstance(rules[0], dict)
    declarations = rules[0]["declarations"]
    assert isinstance(declarations, list) and isinstance(declarations[0], dict)
    rules[0]["declarations"] = NeverIterate([declarations[0]] * 4)
    inspection = map_element_report(
        report,
        lambda _path: source_snapshot(".x { color: red }"),
        generation=4,
        max_rules=10,
        max_declarations=10,
        max_rule_declarations=3,
    )
    assert inspection.rules == ()
    assert inspection.truncated is True


def test_element_report_rejects_rule_over_per_rule_declaration_limit() -> None:
    """Pojedyncza reguła ponad per-rule cap nie tworzy tysięcy dzieci Qt."""
    report = _report((0,))
    rules = report["rules"]
    assert isinstance(rules, list) and isinstance(rules[0], dict)
    declarations = rules[0]["declarations"]
    assert isinstance(declarations, list) and isinstance(declarations[0], dict)
    rules[0]["declarations"] = declarations * 4
    inspection = map_element_report(
        report,
        lambda _path: source_snapshot(".x { color: red }"),
        generation=4,
        max_rules=10,
        max_declarations=10,
        max_rule_declarations=3,
    )
    assert inspection.rules == ()
    assert inspection.truncated is True


def test_element_report_accepts_exact_per_rule_declaration_limit() -> None:
    """Dokładnie per-rule cap zachowuje pełną regułę bez truncation."""
    report = _report((0,))
    rules = report["rules"]
    assert isinstance(rules, list) and isinstance(rules[0], dict)
    declarations = rules[0]["declarations"]
    assert isinstance(declarations, list) and isinstance(declarations[0], dict)
    rules[0]["declarations"] = declarations * 3
    inspection = map_element_report(
        report,
        lambda _path: source_snapshot(".x { color: red }"),
        generation=4,
        max_rules=10,
        max_declarations=10,
        max_rule_declarations=3,
    )
    assert len(inspection.rules) == 1
    assert len(inspection.rules[0].declarations) == 3
    assert inspection.truncated is False


def test_missing_stylesheet_source_is_negatively_cached() -> None:
    """Wiele reguł z brakującego arkusza wywołuje provider tylko raz."""
    report = _report((0,))
    rules = report["rules"]
    assert isinstance(rules, list)
    report["rules"] = rules * 3
    calls = 0

    def missing(_path: str) -> None:
        nonlocal calls
        calls += 1

    inspection = map_element_report(report, missing, generation=4)
    assert len(inspection.rules) == 3
    assert calls == 1


def test_element_report_bounds_untrusted_metadata_before_model_copy() -> None:
    """Metadane poza rules/declarations mają własne cardinality i text caps."""
    report = _report((0,))
    rules = report["rules"]
    assert isinstance(rules, list) and isinstance(rules[0], dict)
    raw = rules[0]
    raw["selector"] = "s" * (MAX_CSS_ELEMENT_REPORT_TEXT_CHARS + 1)
    raw["rule_path"] = list(range(MAX_CSS_ELEMENT_REPORT_PATH_DEPTH + 1))
    raw["contexts"] = [
        {"type": "media", "condition": "c" * (MAX_CSS_ELEMENT_REPORT_TEXT_CHARS + 1)}
    ] * (MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS + 1)
    raw["specificity"] = [1] * (MAX_CSS_ELEMENT_REPORT_PATH_DEPTH + 1)
    declarations = raw["declarations"]
    assert isinstance(declarations, list) and isinstance(declarations[0], dict)
    declarations[0]["declared"] = "d" * (MAX_CSS_ELEMENT_REPORT_TEXT_CHARS + 1)
    declarations[0]["computed"] = "v" * (MAX_CSS_ELEMENT_REPORT_TEXT_CHARS + 1)
    report["breadcrumb"] = ["b"] * (MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS + 1)
    element = report["element"]
    assert isinstance(element, dict)
    element["classes"] = ["c"] * (MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS + 1)
    report["limitations"] = [
        f"limit-{index}" for index in range(MAX_CSS_ELEMENT_REPORT_LIMITATIONS + 1)
    ]
    report["inherited"] = [
        {"property": f"p{index}", "computed": "x", "from": "body"}
        for index in range(MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS + 1)
    ]
    source_calls = 0

    def source_provider(_path: str):  # type: ignore[no-untyped-def]
        nonlocal source_calls
        source_calls += 1
        return source_snapshot(".x { color: red }")

    inspection = map_element_report(report, source_provider, generation=4)
    rule = inspection.rules[0]
    assert source_calls == 0
    assert rule.identity is None
    assert len(rule.selector) <= MAX_CSS_ELEMENT_REPORT_TEXT_CHARS
    assert len(rule.rule_path) <= MAX_CSS_ELEMENT_REPORT_PATH_DEPTH
    assert len(rule.contexts) <= MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS
    assert len(rule.specificity) <= MAX_CSS_ELEMENT_REPORT_PATH_DEPTH
    assert len(rule.declarations[0].declared) <= MAX_CSS_ELEMENT_REPORT_TEXT_CHARS
    assert len(rule.declarations[0].computed) <= MAX_CSS_ELEMENT_REPORT_TEXT_CHARS
    assert inspection.element is not None
    assert len(inspection.element.breadcrumb) <= MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS
    assert len(inspection.element.classes) <= MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS
    assert len(inspection.inherited) <= MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS
    assert len(inspection.limitations) <= MAX_CSS_ELEMENT_REPORT_LIMITATIONS
    assert inspection.truncated is True


def test_webengine_report_bounds_metadata_before_json_transport() -> None:
    """Generated JS ogranicza limitations, ścieżki DOM i listy tekstowe przed return."""
    assert "const addLimitation" in INSPECT_SCRIPT
    assert "limitations: Array.from(limitations).slice(0, maxLimitations)" in INSPECT_SCRIPT
    assert "breadcrumb.length < maxMetadataItems" in INSPECT_SCRIPT
    assert "boundedList(element.classList" in INSPECT_SCRIPT
    assert "boundedText(rule.selectorText)" in INSPECT_SCRIPT
    assert "if (++scannedRules > maxScannedRules)" in INSPECT_SCRIPT
    assert "rule.style.length > maxRuleDeclarations" in INSPECT_SCRIPT
    assert "if (inspectionAborted)" in INSPECT_SCRIPT
    assert "Array.from(n.classList" not in INSPECT_SCRIPT
    assert "++scannedSheets > maxScannedRules" in INSPECT_SCRIPT
    assert "for (const face of document.fonts)" in INSPECT_SCRIPT
    assert "const addLimitationValue" in INSPECT_SCRIPT


def test_unavailable_element_report_bounds_error_and_limitations() -> None:
    """Ścieżka błędu stosuje te same text/cardinality caps co raport dostępny."""
    report = {
        "available": False,
        "error": "e" * (MAX_CSS_ELEMENT_REPORT_TEXT_CHARS + 1),
        "limitations": [
            f"limit-{index}" for index in range(MAX_CSS_ELEMENT_REPORT_LIMITATIONS + 1)
        ],
    }
    inspection = map_element_report(report, lambda _path: None, generation=1)
    assert inspection.available is False
    assert inspection.error is not None
    assert len(inspection.error) <= MAX_CSS_ELEMENT_REPORT_TEXT_CHARS
    assert len(inspection.limitations) <= MAX_CSS_ELEMENT_REPORT_LIMITATIONS
    assert any("ograniczył" in item for item in inspection.limitations)
    assert inspection.truncated is True
