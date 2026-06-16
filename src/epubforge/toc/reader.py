"""Odczyt istniejącego spisu treści z EPUB-a (nav.xhtml z fallbackiem do NCX)."""

from __future__ import annotations

import posixpath
from typing import Literal

from lxml import etree

from epubforge.core import Epub
from epubforge.toc._xml import (
    EPUB_TYPE,
    children_by_localname,
    first_by_localname,
    join_href,
    localname,
    normalized_text,
    parse_xml,
    resolve_internal,
)
from epubforge.toc.model import TocEntry

TocSource = Literal["nav", "ncx", "none"]

_NCX_MEDIA_TYPE = "application/x-dtbncx+xml"


def read_toc(epub: Epub) -> tuple[list[TocEntry], TocSource]:
    """Czyta spis treści EPUB-a: najpierw nav.xhtml, w razie braku — toc.ncx.

    Returns:
        Krotka ``(wpisy, źródło)`` gdzie źródło to ``"nav"``, ``"ncx"`` albo
        ``"none"`` (gdy nie udało się odczytać żadnego spisu). ``href`` wpisów to
        ścieżki **wewnątrz archiwum** (znormalizowane), z opcjonalnym fragmentem.
    """
    nav_entries = _read_nav(epub)
    if nav_entries is not None:
        return nav_entries, "nav"
    ncx_entries = _read_ncx(epub)
    if ncx_entries is not None:
        return ncx_entries, "ncx"
    return [], "none"


def _read_nav(epub: Epub) -> list[TocEntry] | None:
    """Czyta ``<nav epub:type="toc">`` z dokumentu nawigacyjnego EPUB 3."""
    nav_item = next(
        (item for item in epub.manifest if "nav" in (item.properties or "").split()), None
    )
    if nav_item is None:
        return None
    nav_path, _ = resolve_internal(epub.opf_dir(), nav_item.href)
    try:
        root, _doctype = parse_xml(epub.read_file(nav_path))
    except (KeyError, ValueError):
        return None

    nav_el = next(
        (el for el in root.iter() if localname(el) == "nav" and el.get(EPUB_TYPE) == "toc"),
        None,
    )
    if nav_el is None:
        return None
    ol = first_by_localname(nav_el, "ol")
    if ol is None:
        return None
    return _parse_ol(ol, posixpath.dirname(nav_path))


def _parse_ol(ol: etree._Element, base_dir: str) -> list[TocEntry]:
    """Parsuje listę ``<ol>``/``<li>`` na wpisy (rekurencyjnie, z zagnieżdżeniem)."""
    entries: list[TocEntry] = []
    for li in children_by_localname(ol, "li"):
        anchor = next((child for child in li if localname(child) in {"a", "span"}), None)
        title = normalized_text(anchor) if anchor is not None else ""
        href = ""
        raw_href = anchor.get("href") if anchor is not None else None
        if raw_href:
            href = join_href(*resolve_internal(base_dir, raw_href))
        sub_ol = next((child for child in li if localname(child) == "ol"), None)
        children = _parse_ol(sub_ol, base_dir) if sub_ol is not None else []
        entries.append(TocEntry(title=title, href=href, children=children))
    return entries


def _read_ncx(epub: Epub) -> list[TocEntry] | None:
    """Czyta ``navMap``/``navPoint`` z klasycznego ``toc.ncx`` (EPUB 2)."""
    ncx_item = next((item for item in epub.manifest if item.media_type == _NCX_MEDIA_TYPE), None)
    if ncx_item is None:
        return None
    ncx_path, _ = resolve_internal(epub.opf_dir(), ncx_item.href)
    try:
        root, _doctype = parse_xml(epub.read_file(ncx_path))
    except (KeyError, ValueError):
        return None
    navmap = first_by_localname(root, "navmap")
    if navmap is None:
        return None
    return _parse_navpoints(navmap, posixpath.dirname(ncx_path))


def _parse_navpoints(parent: etree._Element, base_dir: str) -> list[TocEntry]:
    """Parsuje ``<navPoint>`` (z zagnieżdżeniem) na wpisy spisu."""
    entries: list[TocEntry] = []
    for navpoint in children_by_localname(parent, "navpoint"):
        label = first_by_localname(navpoint, "navlabel")
        text_el = first_by_localname(label, "text") if label is not None else None
        title = normalized_text(text_el) if text_el is not None else ""
        content = next((child for child in navpoint if localname(child) == "content"), None)
        src = content.get("src") if content is not None else None
        href = join_href(*resolve_internal(base_dir, src)) if src else ""
        children = _parse_navpoints(navpoint, base_dir)
        entries.append(TocEntry(title=title, href=href, children=children))
    return entries
