"""Zapis spisu treści do EPUB-a: nav.xhtml (EPUB 3) i toc.ncx (EPUB 2)."""

from __future__ import annotations

import posixpath
from typing import cast

from lxml import etree

from epubforge.core import Epub
from epubforge.toc._xml import (
    EPUB_NS,
    EPUB_TYPE,
    NCX_NS,
    OPF_NS,
    first_by_localname,
    localname,
    parse_xml,
    relative_href,
    resolve_internal,
    serialize_xml,
    split_fragment,
)
from epubforge.toc.model import TocEntry

_XHTML_NS = "http://www.w3.org/1999/xhtml"
_NCX_MEDIA_TYPE = "application/x-dtbncx+xml"
_XHTML_MEDIA_TYPE = "application/xhtml+xml"
_NCX_DOCTYPE = (
    '<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" '
    '"http://www.daisy.org/z3986/2005/ncx/ncx-2005-1.dtd">'
)


def write_toc(
    epub: Epub,
    entries: list[TocEntry],
    *,
    write_nav: bool = True,
    write_ncx: bool = True,
) -> None:
    """Zapisuje spis treści do bufora EPUB-a (utrwala dopiero ``epub.save()``).

    Args:
        epub: otwarty EPUB.
        entries: drzewo wpisów (``href`` jako ścieżki wewnątrz archiwum).
        write_nav: zapisz dokument nawigacyjny EPUB 3 (nav.xhtml).
        write_ncx: zapisz klasyczny toc.ncx (EPUB 2) i wepnij go w spine.
    """
    if write_nav:
        _write_nav(epub, entries)
    if write_ncx:
        _write_ncx(epub, entries)


# ── nav.xhtml ───────────────────────────────────────────────────────────────


def _write_nav(epub: Epub, entries: list[TocEntry]) -> None:
    """Podmienia ``<nav epub:type="toc">`` lub tworzy nowy dokument nawigacyjny."""
    nav_item = next(
        (item for item in epub.manifest if "nav" in (item.properties or "").split()), None
    )
    if nav_item is not None:
        nav_path, _ = resolve_internal(epub.opf_dir(), nav_item.href)
        try:
            _update_existing_nav(epub, nav_path, entries)
        except KeyError:
            _write_nav_document(epub, nav_path, entries)
        return
    _create_nav(epub, entries)


def _update_existing_nav(epub: Epub, nav_path: str, entries: list[TocEntry]) -> None:
    """Wczytuje istniejący nav, podmienia w nim TYLKO listę spisu i zapisuje."""
    root, doctype = parse_xml(epub.read_file(nav_path))
    nav_el = next(
        (el for el in root.iter() if localname(el) == "nav" and el.get(EPUB_TYPE) == "toc"),
        None,
    )
    if nav_el is None:
        body = first_by_localname(root, "body")
        host = body if body is not None else root
        nav_el = etree.SubElement(host, f"{{{_XHTML_NS}}}nav")
        nav_el.set(EPUB_TYPE, "toc")
    for child in list(nav_el):
        if localname(child) == "ol":
            nav_el.remove(child)
    nav_el.append(_build_ol(entries, posixpath.dirname(nav_path)))
    epub.write_file(nav_path, serialize_xml(root, doctype))


def _create_nav(epub: Epub, entries: list[TocEntry]) -> None:
    """Tworzy pełny nav.xhtml obok OPF i dopisuje go do manifestu (spine nietknięty)."""
    opf_dir = epub.opf_dir()
    nav_path = posixpath.normpath(posixpath.join(opf_dir, "nav.xhtml")) if opf_dir else "nav.xhtml"

    _write_nav_document(epub, nav_path, entries)
    href = relative_href(nav_path, "", opf_dir)
    _add_manifest_item(
        epub, item_id="nav", href=href, media_type=_XHTML_MEDIA_TYPE, properties="nav"
    )


def _write_nav_document(epub: Epub, nav_path: str, entries: list[TocEntry]) -> None:
    """Tworzy nav pod wskazaną ścieżką, bez modyfikowania manifestu."""

    nav_nsmap = cast("dict[str, str]", {None: _XHTML_NS, "epub": EPUB_NS})
    html = etree.Element(f"{{{_XHTML_NS}}}html", nsmap=nav_nsmap)
    head = etree.SubElement(html, f"{{{_XHTML_NS}}}head")
    etree.SubElement(head, f"{{{_XHTML_NS}}}title").text = "Spis treści"
    body = etree.SubElement(html, f"{{{_XHTML_NS}}}body")
    nav_el = etree.SubElement(body, f"{{{_XHTML_NS}}}nav")
    nav_el.set(EPUB_TYPE, "toc")
    nav_el.append(_build_ol(entries, posixpath.dirname(nav_path)))

    epub.write_file(nav_path, serialize_xml(html, "<!DOCTYPE html>"))


def _build_ol(entries: list[TocEntry], start_dir: str) -> etree._Element:
    """Buduje element ``<ol>`` z wpisów (href względne do ``start_dir``)."""
    ol = etree.Element(f"{{{_XHTML_NS}}}ol")
    for entry in entries:
        li = etree.SubElement(ol, f"{{{_XHTML_NS}}}li")
        anchor = etree.SubElement(li, f"{{{_XHTML_NS}}}a")
        path, fragment = split_fragment(entry.href)
        anchor.set("href", relative_href(path, fragment, start_dir))
        anchor.text = entry.title
        if entry.children:
            li.append(_build_ol(entry.children, start_dir))
    return ol


# ── toc.ncx ───────────────────────────────────────────────────────────────--


def _write_ncx(epub: Epub, entries: list[TocEntry]) -> None:
    """Pełna regeneracja toc.ncx + wpis w manifeście + atrybut ``spine@toc``."""
    opf_dir = epub.opf_dir()
    ncx_item = next((item for item in epub.manifest if item.media_type == _NCX_MEDIA_TYPE), None)
    if ncx_item is not None:
        ncx_path, _ = resolve_internal(opf_dir, ncx_item.href)
        ncx_id = ncx_item.id
    else:
        ncx_path = posixpath.normpath(posixpath.join(opf_dir, "toc.ncx")) if opf_dir else "toc.ncx"
        ncx_id = _add_manifest_item(
            epub,
            item_id="ncx",
            href=relative_href(ncx_path, "", opf_dir),
            media_type=_NCX_MEDIA_TYPE,
        )
    meta = epub.metadata
    ncx_xml = _build_ncx(entries, posixpath.dirname(ncx_path), meta.identifier, meta.title)
    epub.write_file(ncx_path, ncx_xml)
    _set_spine_toc(epub, ncx_id)


def _build_ncx(entries: list[TocEntry], start_dir: str, uid: str, title: str) -> bytes:
    """Buduje kompletny dokument NCX (head/docTitle/navMap z playOrder DFS)."""
    ncx_nsmap = cast("dict[str, str]", {None: NCX_NS})
    ncx = etree.Element(f"{{{NCX_NS}}}ncx", nsmap=ncx_nsmap, version="2005-1")
    head = etree.SubElement(ncx, f"{{{NCX_NS}}}head")
    etree.SubElement(head, f"{{{NCX_NS}}}meta", name="dtb:uid", content=uid or "unknown")
    etree.SubElement(head, f"{{{NCX_NS}}}meta", name="dtb:depth", content=str(_depth(entries)))
    doc_title = etree.SubElement(ncx, f"{{{NCX_NS}}}docTitle")
    etree.SubElement(doc_title, f"{{{NCX_NS}}}text").text = title or "Spis treści"
    nav_map = etree.SubElement(ncx, f"{{{NCX_NS}}}navMap")
    _append_navpoints(nav_map, entries, start_dir, [0])
    return serialize_xml(ncx, _NCX_DOCTYPE)


def _append_navpoints(
    parent: etree._Element, entries: list[TocEntry], start_dir: str, order: list[int]
) -> None:
    """Dokleja ``<navPoint>`` (rekurencyjnie) z rosnącym ``playOrder`` (DFS)."""
    for entry in entries:
        order[0] += 1
        play_order = order[0]
        navpoint = etree.SubElement(parent, f"{{{NCX_NS}}}navPoint")
        navpoint.set("id", f"navPoint-{play_order}")
        navpoint.set("playOrder", str(play_order))
        label = etree.SubElement(navpoint, f"{{{NCX_NS}}}navLabel")
        etree.SubElement(label, f"{{{NCX_NS}}}text").text = entry.title
        content = etree.SubElement(navpoint, f"{{{NCX_NS}}}content")
        path, fragment = split_fragment(entry.href)
        content.set("src", relative_href(path, fragment, start_dir))
        _append_navpoints(navpoint, entry.children, start_dir, order)


def _depth(entries: list[TocEntry]) -> int:
    """Maksymalna głębokość drzewa (dla ``dtb:depth``)."""
    return max((1 + _depth(entry.children) for entry in entries), default=0)


# ── OPF (manifest / spine) ────────────────────────────────────────────────--


def _add_manifest_item(
    epub: Epub,
    *,
    item_id: str,
    href: str,
    media_type: str,
    properties: str | None = None,
) -> str:
    """Dodaje ``<item>`` do manifestu OPF (z unikalnym id) i zwraca jego id."""
    root, doctype = parse_xml(epub.read_file(epub.opf_path))
    manifest = root.find(f"{{{OPF_NS}}}manifest")
    if manifest is None:
        manifest = etree.SubElement(root, f"{{{OPF_NS}}}manifest")
    existing = {el.get("id") for el in manifest if el.get("id")}
    unique_id = _unique_id(item_id, existing)
    item = etree.SubElement(manifest, f"{{{OPF_NS}}}item")
    item.set("id", unique_id)
    item.set("href", href)
    item.set("media-type", media_type)
    if properties is not None:
        item.set("properties", properties)
    epub.write_file(epub.opf_path, serialize_xml(root, doctype))
    return unique_id


def _set_spine_toc(epub: Epub, ncx_id: str) -> None:
    """Ustawia atrybut ``toc`` na ``<spine>`` (jeśli brak), wskazując NCX."""
    root, doctype = parse_xml(epub.read_file(epub.opf_path))
    spine = root.find(f"{{{OPF_NS}}}spine")
    if spine is None or spine.get("toc"):
        return
    spine.set("toc", ncx_id)
    epub.write_file(epub.opf_path, serialize_xml(root, doctype))


def _unique_id(base: str, existing: set[str | None]) -> str:
    """Zwraca ``base`` lub ``base-N``, gdy id już zajęte."""
    if base not in existing:
        return base
    suffix = 2
    while f"{base}-{suffix}" in existing:
        suffix += 1
    return f"{base}-{suffix}"
