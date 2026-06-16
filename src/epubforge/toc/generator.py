"""Generowanie spisu treści z nagłówków dokumentów spine (h1..h{max_level})."""

from __future__ import annotations

from dataclasses import dataclass

from epubforge.core import Epub
from epubforge.toc._xml import (
    collect_ids,
    iter_by_localname,
    join_href,
    localname,
    normalized_text,
    parse_xml,
    resolve_internal,
    serialize_xml,
)
from epubforge.toc.model import TocEntry

_DEFAULT_MAX_LEVEL = 3
_ID_PREFIX = "efh-"


@dataclass
class _Heading:
    """Nagłówek znaleziony w dokumencie: poziom, tytuł i docelowy href."""

    level: int
    title: str
    href: str


def generate_toc(epub: Epub, max_level: int = _DEFAULT_MAX_LEVEL) -> list[TocEntry]:
    """Buduje drzewo spisu treści z nagłówków dokumentów spine (w kolejności).

    Dokumenty przetwarzane są w kolejności spine. W każdym zbierane są nagłówki
    ``h1``..``h{max_level}``; brakujące ``id`` są wstrzykiwane (``efh-NNNN``,
    licznik per plik) i plik jest zapisywany z zachowaniem deklaracji XML i
    DOCTYPE. Pierwszy nagłówek pliku linkuje do pliku bez fragmentu. Pliki bez
    nagłówków są pomijane. Ponowne uruchomienie jest idempotentne (id już są).

    Args:
        epub: otwarty EPUB.
        max_level: najgłębszy uwzględniany poziom nagłówka (1-6).

    Returns:
        Lista wpisów najwyższego poziomu (drzewo).
    """
    max_level = max(1, min(6, max_level))
    headings: list[_Heading] = []
    for internal_path in _spine_paths(epub):
        headings.extend(_headings_from_doc(epub, internal_path, max_level))
    return _build_tree(headings)


def _spine_paths(epub: Epub) -> list[str]:
    """Zwraca ścieżki wewnętrzne dokumentów w kolejności spine."""
    by_id = {item.id: item for item in epub.manifest}
    paths: list[str] = []
    for idref in epub.spine:
        item = by_id.get(idref)
        if item is None:
            continue
        path, _ = resolve_internal(epub.opf_dir(), item.href)
        paths.append(path)
    return paths


def _headings_from_doc(epub: Epub, internal_path: str, max_level: int) -> list[_Heading]:
    """Zbiera nagłówki z jednego dokumentu, wstrzykując brakujące ``id``."""
    try:
        root, doctype = parse_xml(epub.read_file(internal_path))
    except (KeyError, ValueError):
        return []
    wanted = {f"h{level}" for level in range(1, max_level + 1)}
    elements = list(iter_by_localname(root, wanted))
    if not elements:
        return []  # plik bez nagłówków — pomijamy

    used_ids = collect_ids(root)
    counter = 0
    headings: list[_Heading] = []
    changed = False
    for index, element in enumerate(elements):
        level = int(localname(element)[1])
        title = normalized_text(element)
        if index == 0:
            # Pierwszy nagłówek pliku — link do pliku bez fragmentu (bez id).
            headings.append(_Heading(level, title, internal_path))
            continue
        anchor_id = element.get("id")
        if not anchor_id:
            anchor_id, counter = _fresh_id(used_ids, counter)
            element.set("id", anchor_id)
            used_ids.add(anchor_id)
            changed = True
        headings.append(_Heading(level, title, join_href(internal_path, anchor_id)))

    if changed:  # zapis tylko gdy faktycznie wstrzyknięto id (idempotencja)
        epub.write_file(internal_path, serialize_xml(root, doctype))
    return headings


def _fresh_id(used_ids: set[str], counter: int) -> tuple[str, int]:
    """Zwraca pierwszy wolny ``efh-NNNN`` (omijając kolizje) i nowy licznik."""
    while True:
        counter += 1
        candidate = f"{_ID_PREFIX}{counter:04d}"
        if candidate not in used_ids:
            return candidate, counter


def _build_tree(headings: list[_Heading]) -> list[TocEntry]:
    """Buduje drzewo wg poziomów; osierocony nagłówek trafia o poziom wyżej."""
    roots: list[TocEntry] = []
    # Stos par (poziom, wpis) — bieżąca ścieżka przodków.
    stack: list[tuple[int, TocEntry]] = []
    for heading in headings:
        entry = TocEntry(title=heading.title, href=heading.href)
        while stack and stack[-1][0] >= heading.level:
            stack.pop()
        if stack:
            stack[-1][1].children.append(entry)
        else:
            roots.append(entry)
        stack.append((heading.level, entry))
    return roots
