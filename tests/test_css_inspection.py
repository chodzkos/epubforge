"""Testy mapowania raportu Chromium na dokładne reguły i rewizje źródła."""

from __future__ import annotations

from epubforge.gui.css_inspection import content_revision, map_element_report, source_snapshot


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
