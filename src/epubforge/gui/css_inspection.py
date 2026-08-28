"""Typowany, bounded model raportu CSSOM i mapowanie reguł na źródło tinycss2."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from epubforge.fixers.css_rules import CssRuleInfo, parse_rules_bounded
from epubforge.gui.css_inspection_bounds import bounded_mapping as _bounded_mapping
from epubforge.gui.css_inspection_bounds import bounded_text as _bounded_text
from epubforge.gui.css_inspection_bounds import bounded_texts as _bounded_texts
from epubforge.gui.css_inspection_bounds import (
    declaration_was_bounded as _declaration_was_bounded,
)
from epubforge.gui.css_inspection_bounds import optional_text as _optional_text
from epubforge.gui.css_inspection_bounds import text_was_bounded as _text_was_bounded
from epubforge.gui.css_inspection_bounds import texts as _texts
from epubforge.gui.resource_limits import (
    MAX_CSS_ELEMENT_REPORT_DECLARATIONS,
    MAX_CSS_ELEMENT_REPORT_LIMITATIONS,
    MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS,
    MAX_CSS_ELEMENT_REPORT_PATH_DEPTH,
    MAX_CSS_ELEMENT_REPORT_RULES,
    MAX_CSS_ELEMENT_REPORT_TEXT_CHARS,
    MAX_CSS_ELEMENT_RULE_DECLARATIONS,
    MAX_CSS_INSPECTOR_DECLARATIONS,
    MAX_CSS_INSPECTOR_RULE_DECLARATIONS,
    MAX_CSS_INSPECTOR_RULES,
    MAX_CSS_INSPECTOR_SOURCE_BYTES,
    utf8_fits,
)

SourceSnapshot = tuple[str, int]
SourceProvider = Callable[[str], SourceSnapshot | None]
_TRUNCATION_MESSAGE = (
    "Inspektor CSS ograniczył liczbę reguł lub deklaracji. Zawęź widok lub użyj filtra."
)


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
    truncated: bool = False


def content_revision(source: str) -> int:
    """Zwraca stabilną 64-bitową rewizję dokładnej treści źródła."""
    return int.from_bytes(hashlib.blake2s(source.encode("utf-8"), digest_size=8).digest(), "big")


def source_snapshot(source: str) -> SourceSnapshot:
    """Buduje parę ``(treść, revision)`` do kontroli konfliktów zapisu."""
    return source, content_revision(source)


def map_element_report(
    report: object,
    source_provider: SourceProvider,
    *,
    generation: int,
    max_rules: int = MAX_CSS_ELEMENT_REPORT_RULES,
    max_declarations: int = MAX_CSS_ELEMENT_REPORT_DECLARATIONS,
    max_rule_declarations: int = MAX_CSS_ELEMENT_RULE_DECLARATIONS,
) -> ElementInspection:
    """Mapuje reguły CSSOM na dokładne pliki/spany bieżących snapshotów.

    Brak mapowania nie usuwa reguły. Trafia ona do wyniku bez ``identity`` oraz
    z jawnym ograniczeniem, dzięki czemu UI nie ukrywa nierozpoznanego przypadku.
    """
    if not isinstance(report, dict) or not report.get("available"):
        error = report.get("error") if isinstance(report, dict) else None
        limits = report.get("limitations", ()) if isinstance(report, dict) else ()
        bounded_limits, limits_truncated = _bounded_texts(
            limits, max_items=MAX_CSS_ELEMENT_REPORT_LIMITATIONS
        )
        error_truncated = error is not None and _text_was_bounded(error)
        truncated = limits_truncated or error_truncated
        if truncated:
            bounded_limits = (
                *bounded_limits[: MAX_CSS_ELEMENT_REPORT_LIMITATIONS - 1],
                _TRUNCATION_MESSAGE,
            )
        return ElementInspection(
            available=False,
            limitations=bounded_limits,
            error=_bounded_text(error) if error else "Computed style wymaga aktywnego WebEngine.",
            truncated=truncated,
        )

    limitation_texts, metadata_truncated = _bounded_texts(
        report.get("limitations", ()), max_items=MAX_CSS_ELEMENT_REPORT_LIMITATIONS
    )
    limitations = list(limitation_texts)
    cache: dict[str, tuple[dict[tuple[int, ...], CssRuleInfo], int] | None] = {}
    mapped_rules: list[InspectorRule] = []
    declaration_count = 0
    truncated = bool(report.get("truncated", False)) or metadata_truncated
    cascade_truncated = bool(report.get("cascade_truncated", report.get("truncated", False)))
    raw_rules = report.get("rules", ())
    if not isinstance(raw_rules, list):
        raw_rules = []
    for raw_index, raw in enumerate(raw_rules):
        if raw_index >= max_rules:
            truncated = True
            cascade_truncated = True
            break
        if not isinstance(raw, dict):
            limitations.append("Nierozpoznany rekord reguły zwrócony przez CSSOM.")
            continue
        raw_declarations = raw.get("declarations", ())
        declaration_items: list[dict[str, Any]] = []
        if isinstance(raw_declarations, (list, tuple)):
            remaining_declarations = max_declarations - declaration_count
            if (
                len(raw_declarations) > max_rule_declarations
                or len(raw_declarations) > remaining_declarations
            ):
                truncated = True
                cascade_truncated = True
                break
            declaration_items.extend(item for item in raw_declarations if isinstance(item, dict))
        declaration_count += len(declaration_items)
        path_value = raw.get("stylesheet_path")
        path_was_bounded = (
            isinstance(path_value, str) and len(path_value) > MAX_CSS_ELEMENT_REPORT_TEXT_CHARS
        )
        path = (
            path_value
            if isinstance(path_value, str)
            and path_value
            and len(path_value) <= MAX_CSS_ELEMENT_REPORT_TEXT_CHARS
            else None
        )
        if path_was_bounded:
            truncated = True
        raw_rule_path = raw.get("rule_path")
        rule_path = _rule_path(raw_rule_path)
        rule_path_was_bounded = (
            isinstance(raw_rule_path, list)
            and len(raw_rule_path) > MAX_CSS_ELEMENT_REPORT_PATH_DEPTH
        )
        if rule_path_was_bounded:
            truncated = True
        selector_value = raw.get("selector", "")
        selector = _bounded_text(selector_value)
        selector_was_bounded = _text_was_bounded(selector_value)
        if selector_was_bounded:
            truncated = True
        inline_path = (
            path_value is None and selector_value == "element.style" and raw_rule_path == ["inline"]
        )
        rule_path_invalid = not inline_path and (
            not isinstance(raw_rule_path, list)
            or not raw_rule_path
            or any(type(item) is not int or item < 0 for item in raw_rule_path)
        )
        if rule_path_invalid:
            truncated = True
        mapping_safe = not (
            path_was_bounded or rule_path_was_bounded or rule_path_invalid or selector_was_bounded
        )
        identity: RuleIdentity | None = None
        source_rule: CssRuleInfo | None = None
        if path is not None and mapping_safe:
            if path in cache:
                parsed = cache[path]
            else:
                snapshot = source_provider(path)
                parsed = None
                if snapshot is not None:
                    source, revision = snapshot
                    if utf8_fits(source, MAX_CSS_INSPECTOR_SOURCE_BYTES):
                        parsed_result = parse_rules_bounded(
                            source,
                            max_rules=MAX_CSS_INSPECTOR_RULES,
                            max_declarations=MAX_CSS_INSPECTOR_DECLARATIONS,
                            max_rule_declarations=MAX_CSS_INSPECTOR_RULE_DECLARATIONS,
                        )
                        parsed = (
                            {item.rule_path: item for item in parsed_result.rules},
                            revision,
                        )
                    else:
                        limitations.append(
                            f"Arkusz zbyt duży do mapowania źródła inspektora: {path}."
                        )
                        parsed = ({}, revision)
                cache[path] = parsed
            if parsed is not None:
                rules, revision = parsed
                source_rule = rules.get(rule_path)
                if source_rule is not None:
                    identity = RuleIdentity(path, rule_path, source_rule.span, generation, revision)
                else:
                    limitations.append(
                        f"Nie zmapowano reguły {path} / {'.'.join(map(str, rule_path))}."
                    )
            else:
                limitations.append(f"Źródło arkusza niedostępne: {path}.")
        elif path is not None and not mapping_safe:
            limitations.append("Reguła ma zbyt duże metadane i pozostaje tylko do odczytu.")
        elif str(raw.get("selector")) != "element.style":
            limitations.append(
                "Reguła z bloku <style> jest widoczna, ale mapowanie jej spanu w XHTML jest tylko do odczytu."
            )
        declarations = tuple(_declaration(item) for item in declaration_items)
        if any(_declaration_was_bounded(item) for item in declaration_items):
            truncated = True
        raw_contexts = raw.get("contexts", ())
        contexts: list[str] = []
        if isinstance(raw_contexts, (list, tuple)):
            if len(raw_contexts) > MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS:
                truncated = True
            for item in raw_contexts[:MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS]:
                if not isinstance(item, dict):
                    continue
                context_type = _bounded_text(item.get("type", ""))
                condition = _bounded_text(item.get("condition", ""))
                if _text_was_bounded(item.get("type", "")) or _text_was_bounded(
                    item.get("condition", "")
                ):
                    truncated = True
                contexts.append(f"@{context_type} {condition}".strip())
        raw_specificity = raw.get("specificity", ())
        specificity = tuple(
            int(value)
            for value in (
                raw_specificity[:MAX_CSS_ELEMENT_REPORT_PATH_DEPTH]
                if isinstance(raw_specificity, (list, tuple))
                else ()
            )
            if isinstance(value, int)
        )
        if (
            isinstance(raw_specificity, (list, tuple))
            and len(raw_specificity) > MAX_CSS_ELEMENT_REPORT_PATH_DEPTH
        ):
            truncated = True
        mapped_rules.append(
            InspectorRule(
                selector=selector,
                stylesheet_path=path,
                rule_path=rule_path,
                contexts=tuple(contexts),
                active=bool(raw.get("active", False)),
                matched=bool(raw.get("matched", False)),
                specificity=specificity,
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
    breadcrumb, breadcrumb_truncated = _bounded_texts(report.get("breadcrumb", ()))
    classes, classes_truncated = _bounded_texts(
        element.get("classes", ()) if isinstance(element, dict) else ()
    )
    truncated = truncated or breadcrumb_truncated or classes_truncated
    if isinstance(element, dict) and any(
        _text_was_bounded(element.get(key, "")) for key in ("tag", "id", "text")
    ):
        truncated = True
    if isinstance(report.get("node_id"), str) and len(str(report["node_id"])) > 240:
        truncated = True
    summary = ElementSummary(
        node_id=_optional_text(report.get("node_id")),
        breadcrumb=breadcrumb,
        tag=_bounded_text(element.get("tag", "")) if isinstance(element, dict) else "",
        element_id=_bounded_text(element.get("id", "")) if isinstance(element, dict) else "",
        classes=classes,
        text=_bounded_text(element.get("text", "")) if isinstance(element, dict) else "",
    )
    fallbacks, fallbacks_truncated = _bounded_texts(
        font.get("fallbacks", ()) if isinstance(font, dict) else ()
    )
    if isinstance(font, dict) and (
        fallbacks_truncated
        or any(
            _text_was_bounded(font.get(key, ""))
            for key in ("used_family", "computed_family", "status")
        )
    ):
        truncated = True
    font_usage = (
        FontUsage(
            used_family=_bounded_text(font.get("used_family", "")),
            computed_family=_bounded_text(font.get("computed_family", "")),
            embedded=bool(font.get("embedded", False)),
            status=_bounded_text(font.get("status", "")),
            fallbacks=fallbacks,
        )
        if isinstance(font, dict)
        else None
    )
    raw_inherited = report.get("inherited", ())
    inherited = tuple(
        {
            "property": _bounded_text(item.get("property", "")),
            "computed": _bounded_text(item.get("computed", "")),
            "from": _bounded_text(item.get("from", "")),
        }
        for item in (
            raw_inherited[:MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS]
            if isinstance(raw_inherited, (list, tuple))
            else ()
        )
        if isinstance(item, dict)
    )
    if (
        isinstance(raw_inherited, (list, tuple))
        and len(raw_inherited) > MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS
    ):
        truncated = True
    if isinstance(raw_inherited, (list, tuple)) and any(
        isinstance(item, dict)
        and any(_text_was_bounded(item.get(key, "")) for key in ("property", "computed", "from"))
        for item in raw_inherited[:MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS]
    ):
        truncated = True
    box, box_truncated = _bounded_mapping(report.get("box", {}))
    reader, reader_truncated = _bounded_mapping(report.get("reader_simulation", {}))
    truncated = truncated or box_truncated or reader_truncated
    limitations.extend(f"Symulator: {item}" for item in _texts(reader.get("limitations", ())))
    if truncated:
        limitations.append(_TRUNCATION_MESSAGE)
    deduplicated_limitations = tuple(dict.fromkeys(limitations))
    if len(deduplicated_limitations) > MAX_CSS_ELEMENT_REPORT_LIMITATIONS:
        truncated = True
        deduplicated_limitations = (
            *deduplicated_limitations[: MAX_CSS_ELEMENT_REPORT_LIMITATIONS - 1],
            _TRUNCATION_MESSAGE,
        )
    return ElementInspection(
        available=True,
        element=summary,
        box=box,
        rules=() if cascade_truncated else tuple(mapped_rules),
        inherited=inherited,
        font=font_usage,
        reader_simulation=reader,
        limitations=deduplicated_limitations,
        truncated=truncated,
    )


def _declaration(raw: dict[str, Any]) -> InspectorDeclaration:
    """Konwertuje jeden nieufny rekord JS na typowany model."""
    winner = raw.get("winner_order")
    return InspectorDeclaration(
        property=_bounded_text(raw.get("property", "")),
        declared=_bounded_text(raw.get("declared", "")),
        computed=_bounded_text(raw.get("computed", "")),
        important=bool(raw.get("important", False)),
        state=_bounded_text(raw.get("state", "lost")),
        winner_order=int(winner) if isinstance(winner, int) else None,
    )


def _rule_path(value: object) -> tuple[int, ...]:
    """Przyjmuje tylko liczbową ścieżkę reguły CSSOM."""
    if not isinstance(value, list):
        return ()
    return tuple(
        item for item in value[:MAX_CSS_ELEMENT_REPORT_PATH_DEPTH] if isinstance(item, int)
    )
