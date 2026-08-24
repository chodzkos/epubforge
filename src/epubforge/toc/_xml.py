"""Wspólne pomocniki XML i ścieżek dla pakietu ``toc`` (czyste, bez Qt).

Parsowanie XHTML/NCX z ``recover=True`` (EPUB-y w praktyce bywają niepoprawne),
zachowanie deklaracji XML **i DOCTYPE** przy serializacji (pułapka: ``tostring``
gubi doctype bez jawnego argumentu) oraz rozwiązywanie ścieżek wewnątrz archiwum.
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterator
from typing import cast

from lxml import etree

from epubforge.core._xml_safe import parse_untrusted_document
from epubforge.core.publication_href import resolve_from_directory

XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
OPF_NS = "http://www.idpf.org/2007/opf"

EPUB_TYPE = f"{{{EPUB_NS}}}type"


def parse_xml(data: bytes) -> tuple[etree._Element, str]:
    """Parsuje dokument (recover) i zwraca ``(root, doctype)`` przez centralne API.

    Delegacja do :func:`epubforge.core._xml_safe.parse_untrusted_document` — jedno
    utwardzone miejsce parsowania treści EPUB (XXE/encje/sieć/DTD wyłączone).

    Raises:
        XmlSecurityError: gdy dokument jest pusty/nieparsowalny albo za duży.
    """
    return parse_untrusted_document(data)


def serialize_xml(root: etree._Element, doctype: str = "") -> bytes:
    """Serializuje element do bajtów z deklaracją XML i (opcjonalnym) DOCTYPE."""
    if doctype:
        return etree.tostring(root, xml_declaration=True, encoding="utf-8", doctype=doctype)
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


def localname(element: etree._Element) -> str:
    """Zwraca lokalną nazwę tagu (bez przestrzeni nazw), małymi literami."""
    tag = cast(object, element.tag)  # dla komentarzy/PI tag bywa wywoływalny, nie str
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def iter_by_localname(root: etree._Element, names: set[str]) -> Iterator[etree._Element]:
    """Iteruje po elementach o danej lokalnej nazwie (dowolna przestrzeń nazw)."""
    for element in root.iter():
        if isinstance(element.tag, str) and localname(element) in names:
            yield element


def children_by_localname(element: etree._Element, name: str) -> list[etree._Element]:
    """Zwraca bezpośrednie dzieci o danej lokalnej nazwie."""
    return [child for child in element if localname(child) == name]


def first_by_localname(element: etree._Element, name: str) -> etree._Element | None:
    """Zwraca pierwszego potomka o danej lokalnej nazwie (DFS) lub ``None``."""
    for descendant in iter_by_localname(element, {name}):
        return descendant
    return None


def collect_ids(root: etree._Element) -> set[str]:
    """Zbiera wszystkie wartości atrybutu ``id`` w dokumencie."""
    ids: set[str] = set()
    for element in root.iter():
        if isinstance(element.tag, str):
            value = element.get("id")
            if value:
                ids.add(value)
    return ids


def normalized_text(element: etree._Element) -> str:
    """Skleja tekst elementu (też z dzieci, np. ``<em>``) i normalizuje białe znaki."""
    return " ".join("".join(str(part) for part in element.itertext()).split())


def split_fragment(href: str) -> tuple[str, str]:
    """Rozdziela ``href`` na ``(ścieżka, fragment)`` (fragment bez ``#``)."""
    path, _, fragment = href.partition("#")
    return path, fragment


def join_href(path: str, fragment: str) -> str:
    """Składa ścieżkę i fragment z powrotem w ``href``."""
    return f"{path}#{fragment}" if fragment else path


def resolve_internal(base_dir: str, href: str) -> tuple[str, str]:
    """Rozwiązuje ``href`` względny do ``base_dir`` na ścieżkę wewnątrz archiwum.

    Returns:
        Krotka ``(ścieżka_wewnętrzna, fragment)``.
    """
    _path, fragment = split_fragment(href)
    return resolve_from_directory(base_dir, href), fragment


def relative_href(internal_path: str, fragment: str, start_dir: str) -> str:
    """Buduje ``href`` względny do ``start_dir`` (RÓŻNE bazy dla nav i ncx)."""
    rel = posixpath.relpath(internal_path, start_dir) if start_dir else internal_path
    return join_href(rel, fragment)
