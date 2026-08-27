"""Granice zasobów dla drzew TOC tworzonych programowo."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from epubforge.core import Epub, ResourceLimitError
from epubforge.toc import (
    TocEntry,
    generate_toc,
    iter_entries,
    move_entry,
    read_toc,
    repair_toc,
    siblings_of,
    validate_toc,
    write_toc,
)

_EXPECTED_MAX_ENTRIES = 20_000
_EXPECTED_MAX_DEPTH = 64
_CONTAINER = b"""<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf"
media-type="application/oebps-package+xml"/></rootfiles></container>"""


def _flat(count: int) -> list[TocEntry]:
    """Buduje płaski model bez kosztownych plików fixture."""
    return [TocEntry(str(index)) for index in range(count)]


def _chain(depth: int) -> list[TocEntry]:
    """Buduje model, w którym korzeń ma głębokość 1."""
    root = TocEntry("0", "OEBPS/text/ch1.xhtml")
    current = root
    for index in range(1, depth):
        child = TocEntry(str(index), "OEBPS/text/ch1.xhtml")
        current.children.append(child)
        current = child
    return [root]


def _write_nav_epub(path: Path, entries: int = 0, *, depth: int = 0) -> Path:
    """Tworzy płaski nav w locie, bez dużego fixture w repozytorium."""
    if depth:
        items = (
            "".join('<ol><li><a href="chapter.xhtml#x">Pozycja</a>' for _ in range(depth))
            + "</li></ol>" * depth
        )
    else:
        items = (
            "<ol>"
            + "".join(
                f'<li><a href="chapter.xhtml#x">Pozycja {index}</a></li>'
                for index in range(entries)
            )
            + "</ol>"
        )
    nav = (
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops"><body>'
        f'<nav epub:type="toc">{items}</nav></body></html>'
    ).encode()
    opf = b"""<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>T</dc:title>
<dc:identifier>id</dc:identifier></metadata><manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="ch" href="chapter.xhtml" media-type="application/xhtml+xml"/>
</manifest><spine/></package>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", _CONTAINER, zipfile.ZIP_STORED)
        archive.writestr("OEBPS/content.opf", opf, zipfile.ZIP_STORED)
        archive.writestr("OEBPS/nav.xhtml", nav, zipfile.ZIP_STORED)
        archive.writestr(
            "OEBPS/chapter.xhtml",
            b'<html xmlns="http://www.w3.org/1999/xhtml"><body id="x"/></html>',
            zipfile.ZIP_STORED,
        )
    return path


def _write_ncx_epub(path: Path, entries: int = 0, *, depth: int = 0) -> Path:
    """Tworzy płaski NCX w locie, bez dużego fixture w repozytorium."""
    if depth:
        points = (
            "".join(
                f'<navPoint id="n{index}"><navLabel><text>Pozycja</text></navLabel>'
                '<content src="chapter.xhtml#x"/>'
                for index in range(depth)
            )
            + "</navPoint>" * depth
        )
    else:
        points = "".join(
            f'<navPoint id="n{index}"><navLabel><text>Pozycja {index}</text></navLabel>'
            '<content src="chapter.xhtml#x"/></navPoint>'
            for index in range(entries)
        )
    ncx = (
        f'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap>{points}</navMap></ncx>'
    ).encode()
    opf = b"""<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>T</dc:title>
<dc:identifier>id</dc:identifier></metadata><manifest>
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
<item id="ch" href="chapter.xhtml" media-type="application/xhtml+xml"/>
</manifest><spine toc="ncx"/></package>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", _CONTAINER, zipfile.ZIP_STORED)
        archive.writestr("OEBPS/content.opf", opf, zipfile.ZIP_STORED)
        archive.writestr("OEBPS/toc.ncx", ncx, zipfile.ZIP_STORED)
        archive.writestr(
            "OEBPS/chapter.xhtml",
            b'<html xmlns="http://www.w3.org/1999/xhtml"><body id="x"/></html>',
            zipfile.ZIP_STORED,
        )
    return path


def _write_heading_epub(path: Path, entries: int) -> Path:
    """Tworzy jeden dokument spine z programowo wygenerowanymi nagłówkami."""
    headings = "".join(f'<h1 id="h{index}">Pozycja {index}</h1>' for index in range(entries))
    chapter = f'<html xmlns="http://www.w3.org/1999/xhtml"><body>{headings}</body></html>'.encode()
    opf = b"""<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>T</dc:title>
<dc:identifier>id</dc:identifier></metadata><manifest>
<item id="ch" href="chapter.xhtml" media-type="application/xhtml+xml"/>
</manifest><spine><itemref idref="ch"/></spine></package>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", _CONTAINER, zipfile.ZIP_STORED)
        archive.writestr("OEBPS/content.opf", opf, zipfile.ZIP_STORED)
        archive.writestr("OEBPS/chapter.xhtml", chapter, zipfile.ZIP_STORED)
    return path


def _write_multi_heading_epub(path: Path, second_doc_entries: int) -> Path:
    """Tworzy dwa dokumenty spine; pierwszy wymaga wstrzyknięcia identyfikatora."""
    first = b"""<html xmlns="http://www.w3.org/1999/xhtml"><body>
<h1>Pierwszy</h1><h1>Drugi</h1></body></html>"""
    headings = "".join(
        f'<h1 id="b{index}">Pozycja {index}</h1>' for index in range(second_doc_entries)
    )
    second = f'<html xmlns="http://www.w3.org/1999/xhtml"><body>{headings}</body></html>'.encode()
    opf = b"""<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>T</dc:title>
<dc:identifier>id</dc:identifier></metadata><manifest>
<item id="a" href="a.xhtml" media-type="application/xhtml+xml"/>
<item id="b" href="b.xhtml" media-type="application/xhtml+xml"/>
</manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", _CONTAINER, zipfile.ZIP_STORED)
        archive.writestr("OEBPS/content.opf", opf, zipfile.ZIP_STORED)
        archive.writestr("OEBPS/a.xhtml", first, zipfile.ZIP_STORED)
        archive.writestr("OEBPS/b.xhtml", second, zipfile.ZIP_STORED)
    return path


def test_validate_rejects_programmatic_entry_limit_plus_one(toc_epub: Path) -> None:
    """Walidacja odrzuca 20 001 wpisów kontrolowanym błędem domenowym."""
    with Epub(toc_epub) as epub, pytest.raises(ResourceLimitError, match="za dużo wpisów"):
        validate_toc(epub, _flat(_EXPECTED_MAX_ENTRIES + 1))


def test_repair_rejects_programmatic_entry_limit_plus_one(toc_epub: Path) -> None:
    """Naprawa nie kopiuje listy większej od wspólnego limitu."""
    with Epub(toc_epub) as epub, pytest.raises(ResourceLimitError, match="za dużo wpisów"):
        repair_toc(epub, _flat(_EXPECTED_MAX_ENTRIES + 1))


def test_write_rejects_programmatic_entry_limit_plus_one_before_mutation(
    toc_epub: Path,
) -> None:
    """Writer odrzuca za duże drzewo przed zmianą nav, NCX lub OPF."""
    with Epub(toc_epub) as epub:
        before = epub.pending_changes()
        with pytest.raises(ResourceLimitError, match="za dużo wpisów"):
            write_toc(epub, _flat(_EXPECTED_MAX_ENTRIES + 1))
        assert epub.pending_changes() == before


def test_nav_reader_rejects_entry_limit_plus_one(tmp_path: Path) -> None:
    """Reader nav zatrzymuje budowę modelu przy wpisie 20 001."""
    path = _write_nav_epub(tmp_path / "nav-too-large.epub", _EXPECTED_MAX_ENTRIES + 1)
    with Epub(path) as epub, pytest.raises(ResourceLimitError, match="za dużo wpisów"):
        read_toc(epub)


def test_ncx_reader_rejects_entry_limit_plus_one(tmp_path: Path) -> None:
    """Reader NCX zatrzymuje budowę modelu przy wpisie 20 001."""
    path = _write_ncx_epub(tmp_path / "ncx-too-large.epub", _EXPECTED_MAX_ENTRIES + 1)
    with Epub(path) as epub, pytest.raises(ResourceLimitError, match="za dużo wpisów"):
        read_toc(epub)


@pytest.mark.parametrize("source", ["nav", "ncx"])
@pytest.mark.parametrize("entries", [100, _EXPECTED_MAX_ENTRIES])
def test_reader_accepts_flat_entry_boundary(tmp_path: Path, source: str, entries: int) -> None:
    """Nav i NCX akceptują zwykły przypadek oraz dokładnie 20 000 wpisów."""
    builder = _write_nav_epub if source == "nav" else _write_ncx_epub
    path = builder(tmp_path / f"{source}-{entries}.epub", entries)
    with Epub(path) as epub:
        result, actual_source = read_toc(epub)
    assert actual_source == source
    assert len(result) == entries


def _walk(entries: list[TocEntry]) -> list[TocEntry]:
    """Spłaszcza małe drzewo iteracyjnie wyłącznie na potrzeby asercji."""
    result: list[TocEntry] = []
    stack = list(reversed(entries))
    while stack:
        entry = stack.pop()
        result.append(entry)
        stack.extend(reversed(entry.children))
    return result


@pytest.mark.parametrize("source", ["nav", "ncx"])
@pytest.mark.parametrize("depth", [_EXPECTED_MAX_DEPTH, _EXPECTED_MAX_DEPTH + 1])
def test_reader_depth_boundary(tmp_path: Path, source: str, depth: int) -> None:
    """Korzeń ma depth=1: poziom 64 przechodzi, poziom 65 jest odrzucany."""
    builder = _write_nav_epub if source == "nav" else _write_ncx_epub
    path = builder(tmp_path / f"{source}-depth-{depth}.epub", depth=depth)
    with Epub(path) as epub:
        if depth == _EXPECTED_MAX_DEPTH:
            entries, actual_source = read_toc(epub)
            assert actual_source == source
            assert len(_walk(entries)) == depth
        else:
            with pytest.raises(ResourceLimitError, match="zbyt głęboki"):
                read_toc(epub)


def test_programmatic_depth_boundary_is_shared_by_core_operations(toc_epub: Path) -> None:
    """Validate/repair/write używają tej samej semantyki depth=1."""
    with Epub(toc_epub) as epub:
        assert validate_toc(epub, _chain(_EXPECTED_MAX_DEPTH)) == []
        repaired, removed = repair_toc(epub, _chain(_EXPECTED_MAX_DEPTH))
        assert len(_walk(repaired)) == _EXPECTED_MAX_DEPTH
        assert removed == []
        for operation in (
            lambda: validate_toc(epub, _chain(_EXPECTED_MAX_DEPTH + 1)),
            lambda: repair_toc(epub, _chain(_EXPECTED_MAX_DEPTH + 1)),
            lambda: write_toc(epub, _chain(_EXPECTED_MAX_DEPTH + 1)),
        ):
            with pytest.raises(ResourceLimitError, match="zbyt głęboki"):
                operation()


def test_programmatic_cycle_is_rejected_without_recursion(toc_epub: Path) -> None:
    """Publicznie mutowalny model z cyklem daje kontrolowany błąd, nie RecursionError."""
    entries = _chain(2)
    entries[0].children[0].children.append(entries[0])
    with Epub(toc_epub) as epub, pytest.raises(ResourceLimitError, match="cykl"):
        validate_toc(epub, entries)


def test_programmatic_alias_is_rejected_as_non_tree(toc_epub: Path) -> None:
    """Ten sam obiekt w dwóch miejscach nie może ominąć polityki drzewa."""
    shared = TocEntry("wspólny")
    with Epub(toc_epub) as epub, pytest.raises(ResourceLimitError, match="w wielu miejscach"):
        validate_toc(epub, [shared, shared])


def test_generate_rejects_entry_limit_plus_one_while_collecting(tmp_path: Path) -> None:
    """Generator nie materializuje listy większej niż wspólny limit TOC."""
    path = _write_heading_epub(tmp_path / "headings-too-large.epub", _EXPECTED_MAX_ENTRIES + 1)
    with Epub(path) as epub, pytest.raises(ResourceLimitError, match="za dużo wpisów"):
        generate_toc(epub, max_level=1)


def test_generate_limit_failure_leaves_all_spine_documents_unchanged(tmp_path: Path) -> None:
    """Globalny limit nie zostawia ID w dokumentach przetworzonych przed błędem."""
    path = _write_multi_heading_epub(
        tmp_path / "multi-headings-too-large.epub", _EXPECTED_MAX_ENTRIES - 1
    )
    with Epub(path) as epub:
        before_pending = epub.pending_changes()
        before_first = epub.read_file("OEBPS/a.xhtml")
        with pytest.raises(ResourceLimitError, match="za dużo wpisów"):
            generate_toc(epub, max_level=1)
        assert epub.pending_changes() == before_pending
        assert epub.read_file("OEBPS/a.xhtml") == before_first


def test_public_iterator_rejects_depth_limit_plus_one() -> None:
    """Publiczny traversal nie kończy się RecursionError na zbyt głębokim modelu."""
    with pytest.raises(ResourceLimitError, match="zbyt głęboki"):
        list(iter_entries(_chain(_EXPECTED_MAX_DEPTH + 1)))


def test_move_rejects_depth_limit_plus_one_and_rolls_back() -> None:
    """D&D nie może zostawić modelu głębszego niż GUI potrafi bezpiecznie obsłużyć."""
    entries = _chain(_EXPECTED_MAX_DEPTH)
    moved = TocEntry("przenoszony")
    entries.append(moved)
    deepest = _walk(entries[:1])[-1]
    with pytest.raises(ResourceLimitError, match="zbyt głęboki"):
        move_entry(entries, moved, deepest, "into")
    assert entries[-1] is moved
    assert deepest.children == []


def test_sibling_lookup_rejects_depth_limit_plus_one() -> None:
    """Nawigacja modelu sprawdza limit przed rekurencyjnym wyszukiwaniem."""
    entries = _chain(_EXPECTED_MAX_DEPTH + 1)
    with pytest.raises(ResourceLimitError, match="zbyt głęboki"):
        siblings_of(entries, entries[0])
