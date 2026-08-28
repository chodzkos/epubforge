"""Czysta logika inspektora CSS (F3+) — bez Qt/gui.

Parsuje arkusz na listę reguł z **offsetami znakowymi** (span), pozwala podmienić
pojedynczą regułę po spanie (jedyna ścieżka zapisu — formatowanie użytkownika
nietykalne) i zbudować podgląd reguły jako fragment HTML dla silnika rich text Qt.

Offsety liczymy z ``source_line``/``source_column`` tokenów tinycss2 (1-indeksowane)
plus tabela offsetów początków linii. Koniec reguły wyznaczamy od **końca ostatniego
tokenu** zawartości skanując do ``}`` — dzięki temu ``}`` w stringach/komentarzach
(np. ``content: "}"``) nie myli granicy, bo siedzi wewnątrz tokenu.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

import tinycss2

# Podzbiór właściwości obsługiwany przez silnik rich text Qt („Supported HTML Subset").
_WHITELIST = {
    "font-family",
    "font-size",
    "font-weight",
    "font-style",
    "color",
    "background-color",
    "text-align",
    "text-indent",
    "line-height",
    "text-decoration",
    "text-transform",
    "margin",
    "margin-top",
    "margin-right",
    "margin-bottom",
    "margin-left",
    "padding",
    "padding-top",
    "padding-right",
    "padding-bottom",
    "padding-left",
}


def _serialize(nodes: object) -> str:
    """Serializuje węzły/tokeny tinycss2 do tekstu (typowane jako ``str``)."""
    return str(tinycss2.serialize(nodes))


_HEADING_RE = re.compile(r"\bh[1-6]\b")
_PARAGRAPH = (
    "Zażółć gęślą jaźń. Pchnąć w tę łódź jeża lub ośm skrzyń fig. "
    "Mężny bądź, chroń pułk twój i sześć flag."
)


@dataclass(frozen=True)
class CssDecl:
    """Pojedyncza deklaracja CSS."""

    name: str
    value: str
    important: bool = False


@dataclass(frozen=True)
class CssRuleInfo:
    """Reguła CSS z offsetem w źródle i metadanymi do podglądu."""

    selector: str
    declarations: list[CssDecl]
    span: tuple[int, int]  # [start, end) — offsety znakowe od selektora do '}' włącznie
    media: str | None = None
    previewable: bool = True
    parse_errors: list[str] = field(default_factory=list)
    # Indeksy reguł w kolejnych ``CSSRuleList``. Tożsamość nie opiera się na
    # selektorze: ten sam selektor może legalnie wystąpić wiele razy.
    rule_path: tuple[int, ...] = ()
    contexts: tuple[str, ...] = ()
    source_line: int = 1
    source_column: int = 1


@dataclass(frozen=True)
class CssRuleParseResult:
    """Bounded model inspektora z jawną informacją o ograniczeniu."""

    rules: tuple[CssRuleInfo, ...]
    truncated: bool = False
    reason: str | None = None


@dataclass
class _ParseBudget:
    """Wewnętrzny licznik pełnych reguł i deklaracji modelu inspektora."""

    max_rules: int
    max_declarations: int
    max_rule_declarations: int | None
    declarations: int = 0
    truncated: bool = False
    reason: str | None = None

    def append(self, rule: CssRuleInfo, rules: list[CssRuleInfo]) -> bool:
        """Dodaje wyłącznie pełną regułę; ``False`` kończy dalsze mapowanie."""
        if len(rules) >= self.max_rules:
            self.truncated = True
            self.reason = "rules"
            return False
        count = len(rule.declarations)
        if self.max_rule_declarations is not None and count > self.max_rule_declarations:
            self.truncated = True
            self.reason = "rule_declarations"
            return False
        if self.declarations + count > self.max_declarations:
            self.truncated = True
            self.reason = "declarations"
            return False
        rules.append(rule)
        self.declarations += count
        return True


# ── Parsowanie arkusza ──────────────────────────────────────────────────────


def parse_rules(source: str) -> list[CssRuleInfo]:
    """Parsuje arkusz na listę reguł z offsetami; ``@media`` spłaszcza rekurencyjnie."""
    rules, _budget = _parse_rules(source, None)
    return rules


def parse_rules_bounded(
    source: str,
    *,
    max_rules: int,
    max_declarations: int,
    max_rule_declarations: int | None = None,
) -> CssRuleParseResult:
    """Buduje bounded model inspektora, nie zmieniając treści ani semantyki spanów."""
    if max_rules < 1 or max_declarations < 1:
        raise ValueError("Limity inspektora CSS muszą być dodatnie.")
    if max_rule_declarations is not None and max_rule_declarations < 1:
        raise ValueError("Limit deklaracji pojedynczej reguły musi być dodatni.")
    budget = _ParseBudget(max_rules, max_declarations, max_rule_declarations)
    rules, _used_budget = _parse_rules(source, budget)
    return CssRuleParseResult(tuple(rules), budget.truncated, budget.reason)


def _parse_rules(
    source: str, budget: _ParseBudget | None
) -> tuple[list[CssRuleInfo], _ParseBudget | None]:
    """Wspólny parser; opcjonalny budżet ogranicza wyłącznie model wynikowy."""
    line_starts = _line_starts(source)
    nodes = tinycss2.parse_stylesheet(source, skip_comments=False, skip_whitespace=False)
    rules: list[CssRuleInfo] = []
    rule_index = 0
    for node in nodes:
        if getattr(node, "type", "") in {"whitespace", "comment", "error"}:
            continue
        keep_going = _collect(
            node,
            source,
            line_starts,
            media=None,
            out=rules,
            rule_path=(rule_index,),
            contexts=(),
            budget=budget,
        )
        if not keep_going:
            break
        rule_index += 1
    return rules, budget


def _collect(
    node: object,
    source: str,
    line_starts: list[int],
    media: str | None,
    out: list[CssRuleInfo],
    rule_path: tuple[int, ...],
    contexts: tuple[str, ...],
    budget: _ParseBudget | None,
) -> bool:
    """Dokłada regułę (lub rekurencyjnie reguły z ``@media``) do listy wynikowej."""
    node_type = getattr(node, "type", "")
    if node_type == "qualified-rule":
        rule = _rule_info(
            node,
            source,
            line_starts,
            media=media,
            previewable=True,
            rule_path=rule_path,
            contexts=contexts,
        )
        if budget is not None:
            return budget.append(rule, out)
        out.append(rule)
        return True
    if node_type == "at-rule":
        keyword = str(getattr(node, "lower_at_keyword", "") or "")
        prelude = _serialize(node.prelude).strip()  # type: ignore[attr-defined]
        context = f"@{keyword} {prelude}".strip()
        # Grupujące at-reguły mają własne CSSRuleList. Parser zachowuje je także
        # dla przypadków ograniczonych w v1, aby żadna reguła nie zniknęła po cichu.
        if (
            keyword in {"media", "supports", "layer", "container", "scope"}
            and getattr(node, "content", None) is not None
        ):
            child_index = 0
            for inner in tinycss2.parse_rule_list(node.content or []):  # type: ignore[attr-defined]
                if getattr(inner, "type", "") in {"whitespace", "comment", "error"}:
                    continue
                keep_going = _collect(
                    inner,
                    source,
                    line_starts,
                    media=prelude if keyword == "media" else media,
                    out=out,
                    rule_path=(*rule_path, child_index),
                    contexts=(*contexts, context),
                    budget=budget,
                )
                if not keep_going:
                    return False
                child_index += 1
        else:
            rule = _rule_info(
                node,
                source,
                line_starts,
                media=media,
                previewable=False,
                rule_path=rule_path,
                contexts=contexts,
            )
            if budget is not None:
                return budget.append(rule, out)
            out.append(rule)
    return True


def _rule_info(
    node: object,
    source: str,
    line_starts: list[int],
    media: str | None,
    previewable: bool,
    rule_path: tuple[int, ...],
    contexts: tuple[str, ...],
) -> CssRuleInfo:
    """Buduje :class:`CssRuleInfo` dla węzła qualified-rule/at-rule."""
    start = _offset(node.source_line, node.source_column, line_starts)  # type: ignore[attr-defined]
    end = _rule_end(node, source, start, line_starts)
    declarations, errors = _declarations(getattr(node, "content", None))
    selector = _selector(node)
    return CssRuleInfo(
        selector=selector,
        declarations=declarations,
        span=(start, end),
        media=media,
        previewable=previewable,
        parse_errors=errors,
        rule_path=rule_path,
        contexts=contexts,
        source_line=int(getattr(node, "source_line", 1) or 1),
        source_column=int(getattr(node, "source_column", 1) or 1),
    )


def _selector(node: object) -> str:
    """Tekst selektora (qualified-rule) albo ``@keyword prelude`` (at-rule)."""
    prelude = _serialize(getattr(node, "prelude", []) or []).strip()
    keyword = getattr(node, "at_keyword", None)
    if keyword:
        return f"@{keyword} {prelude}".strip()
    return prelude


def _rule_end(node: object, source: str, start: int, line_starts: list[int]) -> int:
    """Offset za zamykającym ``}`` (albo ``;`` dla at-reguł bez bloku)."""
    content = getattr(node, "content", None)
    if content is None:  # at-reguła instrukcyjna, np. @import ...;
        semicolon = source.find(";", start)
        return semicolon + 1 if semicolon != -1 else _fallback_end(node, source, start)
    if content:
        last = content[-1]
        scan_from = _offset(last.source_line, last.source_column, line_starts) + len(
            _serialize([last])
        )
    else:
        brace = source.find("{", start)
        scan_from = brace + 1 if brace != -1 else start
    close = source.find("}", scan_from)
    return close + 1 if close != -1 else _fallback_end(node, source, start)


def _fallback_end(node: object, source: str, start: int) -> int:
    """Awaryjny koniec spanu z długości serializacji węzła."""
    return min(len(source), start + len(_serialize([node])))


def _declarations(content: object) -> tuple[list[CssDecl], list[str]]:
    """Parsuje deklaracje bloku; zwraca ``(deklaracje, błędy_parsera)``."""
    decls: list[CssDecl] = []
    errors: list[str] = []
    if content is None:
        return decls, errors
    for item in tinycss2.parse_declaration_list(content, skip_comments=True, skip_whitespace=True):
        if item.type == "declaration":
            value = _serialize(item.value).strip()
            if not value:  # np. „color:" bez wartości — niepoprawna deklaracja
                errors.append(f"Pusta wartość deklaracji: {item.name}")
                continue
            decls.append(CssDecl(name=item.name, value=value, important=item.important))
        elif item.type == "error":
            errors.append(str(item.message))
    return decls, errors


def replace_rule(source: str, span: tuple[int, int], new_text: str) -> str:
    """Podmienia fragment ``source[start:end]`` na ``new_text`` (jedyna modyfikacja)."""
    start, end = span
    return source[:start] + new_text + source[end:]


def parse_single_rule(text: str) -> CssRuleInfo | list[str]:
    """Parsuje pojedynczą regułę; zwraca :class:`CssRuleInfo` albo listę błędów."""
    rules = parse_rules(text)
    errors: list[str] = []
    for rule in rules:
        errors.extend(rule.parse_errors)
    if not rules:
        errors.append("Brak reguły CSS")
    elif len(rules) != 1:
        errors.append("Edytor reguły przyjmuje dokładnie jedną regułę CSS")
    if errors:
        return errors
    return rules[0]


# ── Podgląd: deklaracje → inline style ──────────────────────────────────────


def declarations_to_preview(decls: list[CssDecl]) -> tuple[str, list[str]]:
    """Zamienia deklaracje na inline ``style`` (whitelist) + listę nieobsługiwanych.

    Świadomie budujemy inline ``style="..."`` (nie selektory w arkuszu), bo silnik
    rich text Qt słabo dopasowuje selektory.
    """
    styles: list[str] = []
    unsupported: list[str] = []
    for decl in decls:
        name = decl.name.strip().lower()
        if name in _WHITELIST:
            styles.append(f"{name}: {_normalize_value(name, decl.value)}")
            if decl.important:
                unsupported.append(f"{decl.name}: !important (podgląd ignoruje !important)")
        else:
            unsupported.append(f"{decl.name}: {decl.value}")
    return "; ".join(styles), unsupported


def _normalize_value(name: str, value: str) -> str:
    """Normalizuje wartość pod silnik Qt (np. font-weight liczbowy → bold/normal)."""
    cleaned = value.strip()
    if name == "font-weight" and cleaned.isdigit():
        return "bold" if int(cleaned) >= 550 else "normal"
    return cleaned


# ── Podgląd: przykładowy tekst i HTML ───────────────────────────────────────


def sample_for_selector(selector: str) -> tuple[str, str]:
    """Dobiera ``(tag, tekst)`` przykładu pasujący do rodzaju selektora."""
    low = selector.lower()
    heading = _HEADING_RE.search(low)
    if heading:
        return heading.group(0), "Rozdział pierwszy"
    if "blockquote" in low or ".quote" in low:
        return "blockquote", "„To zdanie jest przykładowym cytatem z książki."
    if re.search(r"\bcode\b", low) or re.search(r"\bpre\b", low):
        return "pre", "def przywitaj(imie):\n    return f'Cześć, {imie}!'"
    return "p", _PARAGRAPH


def build_preview_html(rule: CssRuleInfo) -> tuple[str, list[str]]:
    """Składa fragment HTML podglądu reguły; zwraca ``(html, nieobsługiwane)``."""
    inline_style, unsupported = declarations_to_preview(rule.declarations)
    tag, text = sample_for_selector(rule.selector)
    escaped = html.escape(text)
    style_attr = f' style="{inline_style}"' if inline_style else ""
    return f"<{tag}{style_attr}>{escaped}</{tag}>", unsupported


# ── Pomocnicze: offsety ─────────────────────────────────────────────────────


def _line_starts(source: str) -> list[int]:
    """Buduje tabelę offsetów znakowych początków linii (linia 1 → indeks 0)."""
    starts = [0]
    for index, char in enumerate(source):
        if char == "\n":
            starts.append(index + 1)
    return starts


def _offset(line: int, column: int, line_starts: list[int]) -> int:
    """Zamienia 1-indeksowane ``(linia, kolumna)`` tinycss2 na offset znakowy."""
    base = line_starts[line - 1] if 1 <= line <= len(line_starts) else 0
    return base + (column - 1)
