"""Model drzewa spisu treści (``TocEntry``) i czysta logika przenoszenia wpisów.

:func:`move_entry` jest **czysta** (operuje wyłącznie na przekazanym drzewie,
deterministycznie) i stanowi fundament drag&drop w GUI — dzięki temu logika
przenoszenia jest testowalna bez symulacji zdarzeń Qt.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

from epubforge.core import ResourceLimitError

MoveMode = Literal["before", "after", "into"]


@dataclass
class TocEntry:
    """Pojedynczy wpis spisu treści (węzeł drzewa).

    Attributes:
        title: tytuł pozycji wyświetlany w spisie.
        href: cel jako ścieżka **wewnątrz archiwum** (opcjonalnie z ``#fragment``).
        children: pozycje podrzędne (zagnieżdżone).
    """

    title: str
    href: str = ""
    children: list[TocEntry] = field(default_factory=list)


def iter_entries(entries: list[TocEntry]) -> Iterator[TocEntry]:
    """Iteruje po wszystkich wpisach drzewa w kolejności DFS (pre-order)."""
    from epubforge.toc.limits import validate_toc_structure

    validate_toc_structure(entries)
    stack: list[Iterator[TocEntry]] = [iter(entries)]
    while stack:
        iterator = stack[-1]
        try:
            entry = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        yield entry
        if entry.children:
            stack.append(iter(entry.children))


def siblings_of(entries: list[TocEntry], node: TocEntry) -> tuple[list[TocEntry], int] | None:
    """Zwraca ``(lista_rodzeństwa, indeks)`` węzła albo ``None``, gdy go nie ma."""
    from epubforge.toc.limits import validate_toc_structure

    validate_toc_structure(entries)
    return _locate(entries, node)


def parent_of(entries: list[TocEntry], node: TocEntry) -> TocEntry | None:
    """Zwraca wpis-rodzic węzła albo ``None`` (gdy jest na najwyższym poziomie)."""
    for entry in iter_entries(entries):
        if any(child is node for child in entry.children):
            return entry
    return None


def _locate(entries: list[TocEntry], node: TocEntry) -> tuple[list[TocEntry], int] | None:
    """Znajduje listę-rodzica i indeks węzła w drzewie (po tożsamości obiektu)."""
    for index, entry in enumerate(entries):
        if entry is node:
            return entries, index
        found = _locate(entry.children, node)
        if found is not None:
            return found
    return None


def _subtree_contains(node: TocEntry, target: TocEntry) -> bool:
    """Czy ``target`` to ``node`` albo dowolny jego potomek."""
    if node is target:
        return True
    return any(_subtree_contains(child, target) for child in node.children)


def move_entry(
    entries: list[TocEntry],
    src: TocEntry,
    dst: TocEntry,
    mode: MoveMode,
) -> list[TocEntry]:
    """Przenosi ``src`` względem ``dst`` (``before``/``after``/``into``).

    Args:
        entries: lista najwyższego poziomu drzewa (modyfikowana w miejscu).
        src: przenoszony wpis (po tożsamości obiektu).
        dst: wpis odniesienia.
        mode: ``before``/``after`` (rodzeństwo dst) lub ``into`` (dziecko dst).

    Returns:
        Ta sama lista najwyższego poziomu (po modyfikacji).

    Raises:
        ValueError: gdy ``src is dst``, gdy ``dst`` leży w poddrzewie ``src``
            (zakaz przeniesienia do własnego potomka) lub gdy któryś z węzłów
            nie należy do drzewa.
    """
    from epubforge.toc.limits import validate_toc_structure

    validate_toc_structure(entries)
    if src is dst:
        raise ValueError("Nie można przenieść wpisu na samego siebie.")
    if _subtree_contains(src, dst):
        raise ValueError("Nie można przenieść wpisu do własnego potomka.")
    if _locate(entries, src) is None or _locate(entries, dst) is None:
        raise ValueError("Wpis źródłowy lub docelowy nie należy do drzewa.")

    src_list, src_index = _locate(entries, src)  # type: ignore[misc]
    src_list.pop(src_index)

    # Po usunięciu src indeksy w jego dawnej liście mogły się przesunąć —
    # lokalizujemy dst ponownie.
    dst_list, dst_index = _locate(entries, dst)  # type: ignore[misc]
    if mode == "into":
        inserted_list = dst.children
        inserted_index = len(inserted_list)
    elif mode == "before":
        inserted_list = dst_list
        inserted_index = dst_index
    else:  # "after"
        inserted_list = dst_list
        inserted_index = dst_index + 1
    inserted_list.insert(inserted_index, src)
    try:
        validate_toc_structure(entries)
    except ResourceLimitError:
        inserted_list.pop(inserted_index)
        src_list.insert(src_index, src)
        raise
    return entries
