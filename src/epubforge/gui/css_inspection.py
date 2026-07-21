"""Typowany model raportu CSSOM i mapowanie reguł na źródło tinycss2.

Chromium pozostaje źródłem computed style, dopasowania i aktywnego layoutu.
Ten moduł jedynie łączy raport przeglądarki ze spanami parsera EpubForge; nie
próbuje implementować kompletnego silnika kaskady.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from epubforge.fixers.css_rules import CssRuleInfo, parse_rules

SourceSnapshot = tuple[str, int]
SourceProvider = Callable[[str], SourceSnapshot | None]


@dataclass(frozen=True)
class RuleIdentity:
    """Tożsamość wystąpienia reguły odporna na duplikaty selektora."""

    stylesheet_path: str
    rule_path: tuple[int, ...]
    span: tuple[int, int]
    generation: int
    revision: int


@dataclass(frozen=True)
class InspectorDeclaration:
    """Deklaracja autora wraz z wynikiem podstawowej kaskady v1."""

    property: str
    declared: str
    computed: str
    important: bool
    state: str
    winner_order: int | None


@dataclass(frozen=True)
class InspectorRule:
    """Dopasowana lub jawnie nieaktywna reguła CSSOM."""

    selector: str
    stylesheet_path: str | None
    rule_path: tuple[int, ...]
    contexts: tuple[str, ...]
    active: bool
    matched: bool
    specificity: tuple[int, ...]
    order: int
    declarations: tuple[InspectorDeclaration, ...]
    identity: RuleIdentity | None = None
    source_line: int | None = None
    source_column: int | None = None
    source_mapped: bool = False
    inline: bool = False


@dataclass(frozen=True)
class ElementSummary:
    """Krótki opis wybranego elementu DOM."""

    node_id: str | None
    breadcrumb: tuple[str, ...]
    tag: str
    element_id: str
    classes: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class FontUsage:
    """Dane fontu dostępne przez WebEngine bez protokołu DevTools."""

    used_family: str
    computed_family: str
    embedded: bool
    status: str
    fallbacks: tuple[str, ...]


@dataclass(frozen=True)
class ElementInspection:
    """Kompletny raport trybu Element gotowy do wyświetlenia."""

    available: bool
    element: ElementSummary | None = None
    box: Mapping[str, Any] = field(default_factory=dict)
    rules: tuple[InspectorRule, ...] = ()
    inherited: tuple[Mapping[str, str], ...] = ()
    font: FontUsage | None = None
    reader_simulation: Mapping[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    error: str | None = None


def content_revision(source: str) -> int:
    """Zwraca stabilną 64-bitową rewizję dokładnej treści źródła."""
    return int.from_bytes(hashlib.blake2s(source.encode("utf-8"), digest_size=8).digest(), "big")


def source_snapshot(source: str) -> SourceSnapshot:
    """Buduje parę ``(treść, revision)`` do kontroli konfliktów zapisu."""
    return source, content_revision(source)


def map_element_report(
    report: object, source_provider: SourceProvider, *, generation: int
) -> ElementInspection:
    """Mapuje reguły CSSOM na dokładne pliki/spany bieżących snapshotów.

    Brak mapowania nie usuwa reguły. Trafia ona do wyniku bez ``identity`` oraz
    z jawnym ograniczeniem, dzięki czemu UI nie ukrywa nierozpoznanego przypadku.
    """
    if not isinstance(report, dict) or not report.get("available"):
        error = report.get("error") if isinstance(report, dict) else None
        limits = report.get("limitations", ()) if isinstance(report, dict) else ()
        return ElementInspection(
            available=False,
            limitations=_texts(limits),
            error=str(error) if error else "Computed style wymaga aktywnego WebEngine.",
        )

    limitations = list(_texts(report.get("limitations", ())))
    cache: dict[str, tuple[list[CssRuleInfo], int]] = {}
    mapped_rules: list[InspectorRule] = []
    raw_rules = report.get("rules", ())
    if not isinstance(raw_rules, list):
        raw_rules = []
    for raw in raw_rules:
        if not isinstance(raw, dict):
            limitations.append("Nierozpoznany rekord reguły zwrócony przez CSSOM.")
            continue
        path_value = raw.get("stylesheet_path")
        path = path_value if isinstance(path_value, str) and path_value else None
        rule_path = _rule_path(raw.get("rule_path"))
        identity: RuleIdentity | None = None
        source_rule: CssRuleInfo | None = None
        if path is not None:
            parsed = cache.get(path)
            if parsed is None:
                snapshot = source_provider(path)
                if snapshot is not None:
                    source, revision = snapshot
                    parsed = (parse_rules(source), revision)
                    cache[path] = parsed
            if parsed is not None:
                rules, revision = parsed
                source_rule = next((item for item in rules if item.rule_path == rule_path), None)
                if source_rule is not None:
                    identity = RuleIdentity(path, rule_path, source_rule.span, generation, revision)
                else:
                    limitations.append(
                        f"Nie zmapowano reguły {path} / {'.'.join(map(str, rule_path))}."
                    )
            else:
                limitations.append(f"Źródło arkusza niedostępne: {path}.")
        elif str(raw.get("selector")) != "element.style":
            limitations.append(
                "Reguła z bloku <style> jest widoczna, ale mapowanie jej spanu w XHTML jest tylko do odczytu."
            )
        declarations = tuple(
            _declaration(item) for item in raw.get("declarations", ()) if isinstance(item, dict)
        )
        mapped_rules.append(
            InspectorRule(
                selector=str(raw.get("selector", "")),
                stylesheet_path=path,
                rule_path=rule_path,
                contexts=tuple(
                    f"@{item.get('type', '')} {item.get('condition', '')}".strip()
                    for item in raw.get("contexts", ())
                    if isinstance(item, dict)
                ),
                active=bool(raw.get("active", False)),
                matched=bool(raw.get("matched", False)),
                specificity=tuple(
                    int(value) for value in raw.get("specificity", ()) if isinstance(value, int)
                ),
                order=int(raw.get("order", 0)),
                declarations=declarations,
                identity=identity,
                source_line=source_rule.source_line if source_rule else None,
                source_column=source_rule.source_column if source_rule else None,
                source_mapped=identity is not None,
                inline=path is None and str(raw.get("selector")) == "element.style",
            )
        )

    element = report.get("element", {})
    font = report.get("font", {})
    summary = ElementSummary(
        node_id=_optional_text(report.get("node_id")),
        breadcrumb=_texts(report.get("breadcrumb", ())),
        tag=str(element.get("tag", "")) if isinstance(element, dict) else "",
        element_id=str(element.get("id", "")) if isinstance(element, dict) else "",
        classes=_texts(element.get("classes", ())) if isinstance(element, dict) else (),
        text=str(element.get("text", "")) if isinstance(element, dict) else "",
    )
    font_usage = (
        FontUsage(
            used_family=str(font.get("used_family", "")),
            computed_family=str(font.get("computed_family", "")),
            embedded=bool(font.get("embedded", False)),
            status=str(font.get("status", "")),
            fallbacks=_texts(font.get("fallbacks", ())),
        )
        if isinstance(font, dict)
        else None
    )
    inherited = tuple(item for item in report.get("inherited", ()) if isinstance(item, dict))
    box = report.get("box", {})
    reader = report.get("reader_simulation", {})
    if isinstance(reader, dict):
        limitations.extend(
            f"Symulator: {item}" for item in _texts(reader.get("limitations", ()))
        )
    return ElementInspection(
        available=True,
        element=summary,
        box=box if isinstance(box, dict) else {},
        rules=tuple(mapped_rules),
        inherited=inherited,
        font=font_usage,
        reader_simulation=reader if isinstance(reader, dict) else {},
        limitations=tuple(dict.fromkeys(limitations)),
    )


def _declaration(raw: dict[str, Any]) -> InspectorDeclaration:
    """Konwertuje jeden nieufny rekord JS na typowany model."""
    winner = raw.get("winner_order")
    return InspectorDeclaration(
        property=str(raw.get("property", "")),
        declared=str(raw.get("declared", "")),
        computed=str(raw.get("computed", "")),
        important=bool(raw.get("important", False)),
        state=str(raw.get("state", "lost")),
        winner_order=int(winner) if isinstance(winner, int) else None,
    )


def _rule_path(value: object) -> tuple[int, ...]:
    """Przyjmuje tylko liczbową ścieżkę reguły CSSOM."""
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, int))


def _texts(value: object) -> tuple[str, ...]:
    """Przyjmuje krótką listę tekstów z wyniku JS."""
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item)[:500] for item in value if isinstance(item, str))


def _optional_text(value: object) -> str | None:
    """Normalizuje opcjonalny tekst z raportu WebEngine."""
    return value[:240] if isinstance(value, str) and value else None
