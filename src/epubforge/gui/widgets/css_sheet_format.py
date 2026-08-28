"""Małe, czyste helpery prezentacji arkusza w inspektorze CSS."""

from __future__ import annotations

from epubforge.fixers.css_rules import CssRuleInfo

_DECL_SHORTCUT_MAX = 60


def declaration_shortcut(rule: CssRuleInfo) -> str:
    """Buduje skrót bez pomocniczego stringa proporcjonalnego do całej reguły."""
    parts: list[str] = []
    length = 0
    for declaration in rule.declarations:
        piece = f"{declaration.name}: {declaration.value}"
        separator = "; " if parts else ""
        if length + len(separator) + len(piece) > _DECL_SHORTCUT_MAX:
            prefix = "".join(parts) + separator + piece
            return prefix[: _DECL_SHORTCUT_MAX - 1] + "…"
        parts.extend((separator, piece))
        length += len(separator) + len(piece)
    return "".join(parts)


def index_for_rule_key(
    rules: list[CssRuleInfo], key: tuple[tuple[int, ...], tuple[int, int]] | None
) -> int | None:
    """Odtwarza wybór konkretnego wystąpienia, także przy duplikatach selektora."""
    if not rules:
        return None
    if key is not None:
        for index, rule in enumerate(rules):
            if (rule.rule_path, rule.span) == key:
                return index
    return 0
