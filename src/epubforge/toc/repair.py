"""Walidacja i naprawa spisu treści: martwe linki i nieistniejące fragmenty."""

from __future__ import annotations

from dataclasses import dataclass

from epubforge.core import Epub
from epubforge.toc._xml import collect_ids, parse_xml, split_fragment
from epubforge.toc.limits import validate_toc_structure
from epubforge.toc.model import TocEntry


@dataclass(frozen=True)
class TocProblem:
    """Problem wykryty w spisie treści.

    Attributes:
        href: cel wpisu (ścieżka wewnątrz archiwum, ewentualnie z fragmentem).
        reason: opis problemu (martwy plik / nieistniejący fragment).
    """

    href: str
    reason: str


class _IdCache:
    """Cache zbiorów ``id`` per plik — parsujemy każdy dokument najwyżej raz."""

    def __init__(self, epub: Epub) -> None:
        self._epub = epub
        self._cache: dict[str, set[str] | None] = {}

    def ids(self, path: str) -> set[str] | None:
        """Zwraca zbiór id pliku albo ``None``, gdy pliku nie ma / nie da się sparsować."""
        if path not in self._cache:
            self._cache[path] = self._load(path)
        return self._cache[path]

    def _load(self, path: str) -> set[str] | None:
        try:
            data = self._epub.read_file(path)
        except KeyError:
            return None
        try:
            root, _doctype = parse_xml(data)
        except ValueError:
            return set()
        return collect_ids(root)


def validate_toc(epub: Epub, entries: list[TocEntry]) -> list[TocProblem]:
    """Zwraca listę problemów: martwy plik docelowy lub nieistniejący fragment.

    Wpisy bez ``href`` (czysto strukturalne) są pomijane.
    """
    validate_toc_structure(entries)
    cache = _IdCache(epub)
    problems: list[TocProblem] = []
    _collect_problems(entries, cache, problems)
    return problems


def _collect_problems(entries: list[TocEntry], cache: _IdCache, problems: list[TocProblem]) -> None:
    """Rekurencyjnie zbiera problemy dla wpisów i ich dzieci."""
    for entry in entries:
        reason = _entry_problem(entry, cache)
        if reason is not None:
            problems.append(TocProblem(href=entry.href, reason=reason))
        _collect_problems(entry.children, cache, problems)


def _entry_problem(entry: TocEntry, cache: _IdCache) -> str | None:
    """Zwraca opis problemu wpisu albo ``None``, gdy cel jest poprawny."""
    if not entry.href:
        return None
    path, fragment = split_fragment(entry.href)
    ids = cache.ids(path)
    if ids is None:
        return f"Plik nie istnieje: {path}"
    if fragment and fragment not in ids:
        return f"Fragment nie istnieje: #{fragment}"
    return None


def repair_toc(epub: Epub, entries: list[TocEntry]) -> tuple[list[TocEntry], list[TocEntry]]:
    """Usuwa wpisy z martwym celem, podciągając ich dzieci na miejsce rodzica.

    Returns:
        Krotka ``(naprawione_drzewo, usunięte_wpisy)``. Usunięte wpisy są
        zwracane „odpięte" od drzewa (bez modyfikowania ich list dzieci, które
        zostały już podciągnięte).
    """
    validate_toc_structure(entries)
    cache = _IdCache(epub)
    removed: list[TocEntry] = []
    repaired = _repair_level(entries, cache, removed)
    return repaired, removed


def _repair_level(
    entries: list[TocEntry], cache: _IdCache, removed: list[TocEntry]
) -> list[TocEntry]:
    """Naprawia jeden poziom: zły wpis znika, a jego (naprawione) dzieci wchodzą wyżej."""
    result: list[TocEntry] = []
    for entry in entries:
        repaired_children = _repair_level(entry.children, cache, removed)
        if _entry_problem(entry, cache) is not None:
            removed.append(entry)
            result.extend(repaired_children)  # podciągnij dzieci na miejsce rodzica
        else:
            entry.children = repaired_children
            result.append(entry)
    return result
