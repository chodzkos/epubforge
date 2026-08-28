"""Testy mapowania raportu Chromium na dokładne reguły i rewizje źródła."""

from __future__ import annotations

import subprocess
import sys

import pytest

import epubforge.gui.css_inspection as inspection_module
from epubforge.gui.css_inspection import content_revision, map_element_report, source_snapshot
from epubforge.gui.css_inspector_limits import (
    CSS_INSPECTOR_WORKER_THRESHOLD_BYTES,
    MAX_CSS_ELEMENT_REPORT_LIMITATIONS,
    MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS,
    MAX_CSS_ELEMENT_REPORT_PATH_DEPTH,
    MAX_CSS_ELEMENT_REPORT_TEXT_CHARS,
    MAX_CSS_ELEMENT_REPORT_TOTAL_ITEMS,
    MAX_CSS_ELEMENT_REPORT_TOTAL_TEXT_CHARS,
    MAX_CSS_INSPECTOR_MAPPING_SOURCE_BYTES,
)
from epubforge.gui.preview.css_bridge import INSPECT_SCRIPT


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


def test_css_report_model_and_bridge_import_without_qt() -> None:
    """Czysty model/JS bridge nie może wymagać opcjonalnego PySide6."""
    code = """
import builtins
real_import = builtins.__import__
def blocked(name, *args, **kwargs):
    if name.startswith('PySide6'):
        raise ModuleNotFoundError(name)
    return real_import(name, *args, **kwargs)
builtins.__import__ = blocked
import epubforge.gui.css_inspection
import epubforge.gui.preview.css_bridge
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr


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


def test_many_unique_missing_sources_have_bounded_provider_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Różne missing paths nie mogą wykonać nieograniczonej liczby odczytów GUI."""
    monkeypatch.setattr(
        inspection_module, "MAX_CSS_INSPECTOR_MAPPING_STYLESHEETS", 2, raising=False
    )
    report = _report((0,))
    raw_rule = report["rules"][0]  # type: ignore[index]
    assert isinstance(raw_rule, dict)
    report["rules"] = [
        {**raw_rule, "stylesheet_path": f"OEBPS/missing-{index}.css"} for index in range(5)
    ]
    calls: list[str] = []

    def missing(path: str) -> None:
        calls.append(path)

    inspection = map_element_report(report, missing, generation=4)

    assert calls == ["OEBPS/missing-0.css", "OEBPS/missing-1.css"]
    assert inspection.truncated is True
    assert any("budżet" in item for item in inspection.limitations)


def test_oversized_source_exhausts_aggregate_before_more_providers_or_full_encode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pierwszy over-budget snapshot kończy dalsze materializowanie arkuszy."""
    budget = 16
    monkeypatch.setattr(inspection_module, "MAX_CSS_INSPECTOR_MAPPING_SOURCE_BYTES", budget)
    monkeypatch.setattr(
        inspection_module, "MAX_CSS_INSPECTOR_MAPPING_STYLESHEETS", 10, raising=False
    )
    report = _report((0,))
    raw_rule = report["rules"][0]  # type: ignore[index]
    assert isinstance(raw_rule, dict)
    report["rules"] = [
        {**raw_rule, "stylesheet_path": f"OEBPS/large-{index}.css"} for index in range(4)
    ]
    provider_calls: list[str] = []
    fit_limits: list[int] = []
    parse_calls = 0

    def provider(path: str):
        provider_calls.append(path)
        return source_snapshot("x" * (budget + 1))

    def bounded_fit(_source: str, max_bytes: int) -> bool:
        fit_limits.append(max_bytes)
        return False

    def parse_forbidden(*_args: object, **_kwargs: object) -> None:
        nonlocal parse_calls
        parse_calls += 1

    monkeypatch.setattr(inspection_module, "utf8_fits", bounded_fit)
    monkeypatch.setattr(inspection_module, "parse_rules_bounded", parse_forbidden)
    inspection = map_element_report(report, provider, generation=4)

    assert provider_calls == ["OEBPS/large-0.css"]
    assert fit_limits == [budget]
    assert parse_calls == 0
    assert inspection.truncated is True
    assert any("budżet" in item for item in inspection.limitations)


def test_mapping_source_aggregate_uses_existing_synchronous_parse_threshold() -> None:
    """Aggregate GUI budget nie przekracza istniejącej granicy pracy synchronicznej."""
    assert MAX_CSS_INSPECTOR_MAPPING_SOURCE_BYTES == CSS_INSPECTOR_WORKER_THRESHOLD_BYTES


def test_mapping_source_aggregate_stops_before_more_providers_and_parses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Suma różnych arkuszy ma cap przed kolejnymi providerami i parserami."""
    source = ".x { color: red }"
    monkeypatch.setattr(
        inspection_module, "MAX_CSS_INSPECTOR_MAPPING_SOURCE_BYTES", len(source.encode("utf-8"))
    )
    report = _report((0,))
    raw_rule = report["rules"][0]  # type: ignore[index]
    assert isinstance(raw_rule, dict)
    report["rules"] = [{**raw_rule, "stylesheet_path": f"OEBPS/{index}.css"} for index in range(4)]
    provider_calls: list[str] = []
    parse_calls = 0
    original_parse = inspection_module.parse_rules_bounded

    def provider(path: str):  # type: ignore[no-untyped-def]
        provider_calls.append(path)
        return source_snapshot(source)

    def counted_parse(text: str, **kwargs: int):  # type: ignore[no-untyped-def]
        nonlocal parse_calls
        parse_calls += 1
        return original_parse(text, **kwargs)

    monkeypatch.setattr(inspection_module, "parse_rules_bounded", counted_parse)
    inspection = map_element_report(report, provider, generation=4)

    assert provider_calls == ["OEBPS/0.css", "OEBPS/1.css"]
    assert parse_calls == 1
    assert inspection.truncated is True
    assert any("łączny budżet" in item for item in inspection.limitations)


def test_mapping_source_aggregate_accepts_exact_total(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dokładnie cały aggregate source budget parsuje wszystkie unikalne arkusze."""
    source = ".x{color:red}"
    source_bytes = len(source.encode("utf-8"))
    monkeypatch.setattr(
        inspection_module, "MAX_CSS_INSPECTOR_MAPPING_SOURCE_BYTES", source_bytes * 2
    )
    report = _report((0,))
    raw_rule = report["rules"][0]  # type: ignore[index]
    assert isinstance(raw_rule, dict)
    report["rules"] = [
        {**raw_rule, "stylesheet_path": "OEBPS/a.css"},
        {**raw_rule, "stylesheet_path": "OEBPS/b.css"},
    ]
    parse_calls = 0
    original_parse = inspection_module.parse_rules_bounded

    def counted_parse(text: str, **kwargs: int):  # type: ignore[no-untyped-def]
        nonlocal parse_calls
        parse_calls += 1
        return original_parse(text, **kwargs)

    monkeypatch.setattr(inspection_module, "parse_rules_bounded", counted_parse)
    inspection = map_element_report(report, lambda _path: source_snapshot(source), generation=4)

    assert parse_calls == 2
    assert inspection.truncated is False


def test_mapping_source_aggregate_limit_plus_one_does_not_parse_next_sheet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unikalny arkusz przekraczający remaining budget nie trafia do parsera."""
    first = ".a{color:red}"
    second = ".b{color:blue}"
    monkeypatch.setattr(
        inspection_module,
        "MAX_CSS_INSPECTOR_MAPPING_SOURCE_BYTES",
        len(first.encode("utf-8")) + len(second.encode("utf-8")) - 1,
    )
    report = _report((0,))
    raw_rule = report["rules"][0]  # type: ignore[index]
    assert isinstance(raw_rule, dict)
    report["rules"] = [
        {**raw_rule, "stylesheet_path": "OEBPS/a.css"},
        {**raw_rule, "stylesheet_path": "OEBPS/b.css"},
    ]
    parse_calls: list[str] = []
    original_parse = inspection_module.parse_rules_bounded

    def provider(path: str):
        return source_snapshot(first if path.endswith("a.css") else second)

    def counted_parse(text: str, **kwargs: int):  # type: ignore[no-untyped-def]
        parse_calls.append(text)
        return original_parse(text, **kwargs)

    monkeypatch.setattr(inspection_module, "parse_rules_bounded", counted_parse)
    inspection = map_element_report(report, provider, generation=4)

    assert parse_calls == [first]
    assert inspection.truncated is True


def test_mapping_source_aggregate_counts_repeated_path_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Powtórzony path korzysta z cache i nie zużywa source budget ponownie."""
    source = ".x{color:red}"
    monkeypatch.setattr(
        inspection_module, "MAX_CSS_INSPECTOR_MAPPING_SOURCE_BYTES", len(source.encode("utf-8"))
    )
    report = _report((0,))
    report["rules"] = report["rules"] * 4  # type: ignore[operator]
    provider_calls = 0
    parse_calls = 0
    original_parse = inspection_module.parse_rules_bounded

    def provider(_path: str):
        nonlocal provider_calls
        provider_calls += 1
        return source_snapshot(source)

    def counted_parse(text: str, **kwargs: int):  # type: ignore[no-untyped-def]
        nonlocal parse_calls
        parse_calls += 1
        return original_parse(text, **kwargs)

    monkeypatch.setattr(inspection_module, "parse_rules_bounded", counted_parse)
    inspection = map_element_report(report, provider, generation=4)

    assert provider_calls == 1
    assert parse_calls == 1
    assert inspection.truncated is False


def test_malformed_declaration_entry_is_explicit() -> None:
    """Pomijana deklaracja ma jawny truncation reason."""
    report = _report((0,))
    report["rules"][0]["declarations"].append("invalid")  # type: ignore[index,union-attr]
    inspection = map_element_report(
        report, lambda _path: source_snapshot(".x { color: red }"), generation=4
    )
    assert inspection.truncated is True
    assert any("declarations" in item for item in inspection.limitations)


def test_malformed_context_entry_is_explicit() -> None:
    """Pomijany context ma jawny truncation reason."""
    report = _report((0,))
    report["rules"][0]["contexts"].append("invalid")  # type: ignore[index,union-attr]
    inspection = map_element_report(
        report, lambda _path: source_snapshot(".x { color: red }"), generation=4
    )
    assert inspection.truncated is True
    assert any("contexts" in item for item in inspection.limitations)


def test_malformed_specificity_member_is_explicit() -> None:
    """Pomijana składowa specificity ma jawny truncation reason."""
    report = _report((0,))
    report["rules"][0]["specificity"].append("invalid")  # type: ignore[index,union-attr]
    inspection = map_element_report(
        report, lambda _path: source_snapshot(".x { color: red }"), generation=4
    )
    assert inspection.truncated is True
    assert any("specificity" in item for item in inspection.limitations)


def test_malformed_inherited_entry_is_explicit() -> None:
    """Pomijany inherited record ma jawny truncation reason."""
    report = _report((0,))
    report["inherited"].append("invalid")  # type: ignore[union-attr]
    inspection = map_element_report(
        report, lambda _path: source_snapshot(".x { color: red }"), generation=4
    )
    assert inspection.truncated is True
    assert any("inherited" in item for item in inspection.limitations)


def test_malformed_text_list_member_is_explicit() -> None:
    """Non-string odrzucony przez bounded_texts nie znika bez limitation."""
    report = _report((0,))
    report["breadcrumb"].append(7)  # type: ignore[union-attr]
    inspection = map_element_report(
        report, lambda _path: source_snapshot(".x { color: red }"), generation=4
    )
    assert inspection.truncated is True
    assert any("metadane tekstowe" in item for item in inspection.limitations)


def test_limitation_overflow_keeps_truncation_reason_deduplicated() -> None:
    """Overflow nie może ponownie dopisać reason zachowanego już w prefiksie."""
    report = _report((0,))
    truncation_message = inspection_module._TRUNCATION_MESSAGE
    report["limitations"] = [
        truncation_message,
        *(f"limit-{index}" for index in range(MAX_CSS_ELEMENT_REPORT_LIMITATIONS - 1)),
    ]
    inspection = map_element_report(report, lambda _path: None, generation=4)

    assert inspection.truncated is True
    assert len(inspection.limitations) == MAX_CSS_ELEMENT_REPORT_LIMITATIONS
    assert inspection.limitations.count(truncation_message) == 1
    assert len(inspection.limitations) == len(set(inspection.limitations))


@pytest.mark.parametrize(
    ("member", "invalid"),
    [
        ("rules", {}),
        ("breadcrumb", {}),
        ("inherited", {}),
    ],
)
def test_malformed_top_level_list_container_is_explicit(member: str, invalid: object) -> None:
    """Kontener raportu o złym typie nie może oznaczać kompletnej inspekcji."""
    report = _report((0,))
    report[member] = invalid
    inspection = map_element_report(
        report, lambda _path: source_snapshot(".x { color: red }"), generation=4
    )
    assert inspection.truncated is True
    assert inspection.limitations


@pytest.mark.parametrize(
    ("member", "invalid"),
    [("declarations", None), ("contexts", {}), ("specificity", {})],
)
def test_malformed_rule_list_container_is_explicit(member: str, invalid: object) -> None:
    """Kontener członka reguły o złym typie daje jawny truncation signal."""
    report = _report((0,))
    report["rules"][0][member] = invalid  # type: ignore[index]
    inspection = map_element_report(
        report, lambda _path: source_snapshot(".x { color: red }"), generation=4
    )
    assert inspection.truncated is True
    assert inspection.limitations


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


def test_webengine_report_has_aggregate_pre_serialization_budget() -> None:
    """Iloczyn capów pól nie może ominąć łącznego budżetu payloadu JSON."""
    assert f"const maxReportTextChars = {MAX_CSS_ELEMENT_REPORT_TOTAL_TEXT_CHARS}" in INSPECT_SCRIPT
    assert f"maxReportItems = {MAX_CSS_ELEMENT_REPORT_TOTAL_ITEMS}" in INSPECT_SCRIPT
    assert "const reserveReportText" in INSPECT_SCRIPT
    assert "const reserveReportItem" in INSPECT_SCRIPT
    assert "JSON.stringify(String(value ?? '')).length - 2" in INSPECT_SCRIPT
    assert "reportTextChars + escapedChars > maxReportTextChars" in INSPECT_SCRIPT
    assert "reportTextChars + escapedChars >= maxReportTextChars" not in INSPECT_SCRIPT
    assert "const reportBudgetCheckpoint" in INSPECT_SCRIPT
    assert "rollbackReportBudget(ruleBudget)" in INSPECT_SCRIPT
    assert "osiągnięcie limitu przerywa zbieranie kaskady" in INSPECT_SCRIPT
    assert "if (!reserveReportItem())" in INSPECT_SCRIPT
    assert INSPECT_SCRIPT.index("if (!reserveReportItem())") < INSPECT_SCRIPT.index(
        "record.declarations.push(decl)"
    )
    final_cleanup = INSPECT_SCRIPT.rindex("if (inspectionAborted)")
    assert final_cleanup > INSPECT_SCRIPT.index("if (document.fonts)")
    assert final_cleanup < INSPECT_SCRIPT.rindex("return result;")
    assert "rules.length = 0" in INSPECT_SCRIPT[final_cleanup:]


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
