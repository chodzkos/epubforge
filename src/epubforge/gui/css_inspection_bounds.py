"""Bounded konwersja nieufnych metadanych raportu CSSOM."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from epubforge.gui.resource_limits import (
    MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS,
    MAX_CSS_ELEMENT_REPORT_TEXT_CHARS,
)


def bounded_text(value: object) -> str:
    """Ogranicza pojedynczy tekst raportu."""
    return str(value)[:MAX_CSS_ELEMENT_REPORT_TEXT_CHARS]


def text_was_bounded(value: object) -> bool:
    """Czy tekst przekracza kontrakt transportu raportu."""
    return len(str(value)) > MAX_CSS_ELEMENT_REPORT_TEXT_CHARS


def bounded_texts(
    value: object,
    *,
    max_items: int = MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS,
) -> tuple[tuple[str, ...], bool]:
    """Kopiuje bounded listę tekstów i raportuje utratę danych."""
    if not isinstance(value, (list, tuple)):
        return (), False
    texts = tuple(
        item[:MAX_CSS_ELEMENT_REPORT_TEXT_CHARS]
        for item in value[:max_items]
        if isinstance(item, str)
    )
    truncated = len(value) > max_items or any(
        isinstance(item, str) and len(item) > MAX_CSS_ELEMENT_REPORT_TEXT_CHARS
        for item in value[:max_items]
    )
    return texts, truncated


def texts(value: object) -> tuple[str, ...]:
    """Zwraca wyłącznie bounded teksty bez osobnego statusu."""
    return bounded_texts(value)[0]


def declaration_was_bounded(raw: dict[str, Any]) -> bool:
    """Czy tekst któregokolwiek pola deklaracji przekracza kontrakt."""
    return any(
        text_was_bounded(raw.get(key, "")) for key in ("property", "declared", "computed", "state")
    )


def bounded_mapping(value: object, *, depth: int = 0) -> tuple[dict[str, Any], bool]:
    """Kopiuje małą strukturę metadanych bez nieograniczonych kluczy/list."""
    if not isinstance(value, Mapping):
        return {}, False
    result: dict[str, Any] = {}
    truncated = False
    for index, (raw_key, raw_value) in enumerate(value.items()):
        if index >= MAX_CSS_ELEMENT_REPORT_METADATA_ITEMS:
            truncated = True
            break
        key = bounded_text(raw_key)
        truncated = truncated or text_was_bounded(raw_key)
        if isinstance(raw_value, Mapping) and depth < 2:
            child, child_truncated = bounded_mapping(raw_value, depth=depth + 1)
            result[key] = child
            truncated = truncated or child_truncated
        elif isinstance(raw_value, (list, tuple)):
            child_texts, child_truncated = bounded_texts(raw_value)
            result[key] = child_texts
            truncated = truncated or child_truncated
        elif isinstance(raw_value, str):
            result[key] = bounded_text(raw_value)
            truncated = truncated or text_was_bounded(raw_value)
        elif isinstance(raw_value, (bool, int, float)) or raw_value is None:
            result[key] = raw_value
        else:
            result[key] = bounded_text(raw_value)
            truncated = truncated or text_was_bounded(raw_value)
    return result, truncated


def optional_text(value: object) -> str | None:
    """Normalizuje krótki opcjonalny identyfikator."""
    return value[:240] if isinstance(value, str) and value else None
