"""Wspólna polityka ograniczeń struktury spisu treści."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from epubforge.core import ResourceLimitError
from epubforge.toc.model import TocEntry

MAX_TOC_ENTRIES = 20_000
MAX_TOC_DEPTH = 64


@dataclass
class TocBudget:
    """Licznik używany podczas budowania drzewa z niezaufanego dokumentu."""

    count: int = 0

    def consume(self, depth: int) -> None:
        """Rezerwuje jeden wpis na danej głębokości albo zgłasza limit."""
        if depth > MAX_TOC_DEPTH:
            raise ResourceLimitError(
                "Spis treści jest zbyt głęboki do bezpiecznego przetworzenia "
                f"({depth} > {MAX_TOC_DEPTH})."
            )
        self.count += 1
        if self.count > MAX_TOC_ENTRIES:
            raise ResourceLimitError(
                f"Spis treści ma za dużo wpisów ({self.count} > {MAX_TOC_ENTRIES})."
            )


def validate_toc_structure(entries: list[TocEntry]) -> None:
    """Sprawdza liczbę, głębokość i drzewiastą tożsamość wpisów iteracyjnie."""
    budget = TocBudget()
    seen: set[int] = set()
    stack: list[tuple[Iterator[TocEntry], int]] = [(iter(entries), 1)]
    while stack:
        iterator, depth = stack[-1]
        try:
            entry = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        identity = id(entry)
        if identity in seen:
            raise ResourceLimitError("Spis treści zawiera cykl lub ten sam wpis w wielu miejscach.")
        seen.add(identity)
        budget.consume(depth)
        if entry.children:
            stack.append((iter(entry.children), depth + 1))
