"""Przepisywanie odwołań publikacji do izolowanego schematu podglądu."""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable
from typing import cast
from urllib.parse import unquote, urlsplit

from lxml import etree

from epubforge.core._xml_safe import parse_untrusted_document, serialize_document
from epubforge.gui.preview.backend import DiagnosticCategory, DiagnosticEvent
from epubforge.gui.preview.dom_mapping import assign_render_node_ids
from epubforge.gui.preview.paths import UnsafePreviewPathError, normalize_internal_path
from epubforge.gui.preview.sanitize import sanitize_xhtml
from epubforge.gui.preview.session import PreviewGeneration
from epubforge.i18n import _

DiagnosticSink = Callable[[DiagnosticEvent], None]
_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
_IMPORT_RE = re.compile(r"(@import\s+)(['\"])(.*?)\2", re.IGNORECASE)
_XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
_URL_ATTRIBUTES = frozenset({"href", "src", "poster", "data"})


def rewrite_xhtml(
    data: bytes,
    generation: PreviewGeneration,
    requester: str,
    report: DiagnosticSink | None = None,
) -> bytes:
    """Sanityzuje XHTML i wersjonuje wszystkie bezpieczne odwołania względne."""
    source_root, source_doctype = parse_untrusted_document(data)
    assign_render_node_ids(source_root, requester)
    clean = sanitize_xhtml(serialize_document(source_root, source_doctype))
    root, doctype = parse_untrusted_document(clean)
    for element in root.iter():
        base = _element_base(element, requester)
        for attribute in list(element.attrib):
            local = etree.QName(attribute).localname.lower()
            if local in _URL_ATTRIBUTES or attribute == _XLINK_HREF:
                original = cast(str, element.attrib[attribute])
                rewritten = resolve_reference(original, base, generation, requester, report)
                if rewritten is not None:
                    element.attrib[attribute] = rewritten
                    if local == "href" and etree.QName(element.tag).localname.lower() == "link":
                        target = _resolved_path(original, base)
                        if target is not None:
                            element.set("data-epubforge-path", target)
            elif local == "style":
                element.attrib[attribute] = rewrite_css_text(
                    cast(str, element.attrib[attribute]), generation, base, requester, report
                )
        if etree.QName(element.tag).localname.lower() == "style" and element.text:
            element.text = rewrite_css_text(element.text, generation, base, requester, report)

    _remove_xml_bases(root)
    return serialize_document(root, doctype)


def rewrite_svg(
    data: bytes,
    generation: PreviewGeneration,
    requester: str,
    report: DiagnosticSink | None = None,
) -> bytes:
    """Usuwa aktywną treść SVG i wersjonuje jego odwołania do zasobów."""
    root, doctype = parse_untrusted_document(data)
    for element in list(root.iter()):
        local_name = etree.QName(element.tag).localname.lower()
        if local_name in {"script", "foreignobject"}:
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
            continue
        base = _element_base(element, requester)
        for attribute in list(element.attrib):
            local = etree.QName(attribute).localname.lower()
            if local.startswith("on"):
                del element.attrib[attribute]
            elif local in _URL_ATTRIBUTES or attribute == _XLINK_HREF:
                original = cast(str, element.attrib[attribute])
                rewritten = resolve_reference(original, base, generation, requester, report)
                if rewritten is not None:
                    element.attrib[attribute] = rewritten
            elif local == "style":
                element.attrib[attribute] = rewrite_css_text(
                    cast(str, element.attrib[attribute]), generation, base, requester, report
                )
    _remove_xml_bases(root)
    return serialize_document(root, doctype)


def rewrite_css(
    data: bytes,
    generation: PreviewGeneration,
    requester: str,
    report: DiagnosticSink | None = None,
) -> bytes:
    """Przepisuje url() i @import bez rozwijania importów, więc cykle obsługuje silnik."""
    text = data.decode("utf-8-sig", errors="replace")
    return rewrite_css_text(text, generation, requester, requester, report).encode("utf-8")


def rewrite_css_text(
    text: str,
    generation: PreviewGeneration,
    base_path: str,
    requester: str,
    report: DiagnosticSink | None = None,
) -> str:
    """Wersjonuje odwołania CSS, zachowując pozostałą składnię bez zmian."""

    def replace_url(match: re.Match[str]) -> str:
        quote_char, value = match.group(1), match.group(2).strip()
        resolved = resolve_reference(value, base_path, generation, requester, report)
        if resolved is None:
            return match.group(0)
        return f"url({quote_char}{resolved}{quote_char})"

    def replace_import(match: re.Match[str]) -> str:
        resolved = resolve_reference(match.group(3), base_path, generation, requester, report)
        if resolved is None:
            return match.group(0)
        return f"{match.group(1)}{match.group(2)}{resolved}{match.group(2)}"

    return _IMPORT_RE.sub(replace_import, _URL_RE.sub(replace_url, text))


def resolve_reference(
    source_url: str,
    base_path: str,
    generation: PreviewGeneration,
    requester: str,
    report: DiagnosticSink | None = None,
) -> str | None:
    """Rozwiązuje względny URL wyłącznie wewnątrz bieżącej publikacji."""
    value = source_url.strip()
    parsed = urlsplit(value)
    if parsed.scheme == "data":
        return value
    if parsed.scheme or parsed.netloc or parsed.query:
        _report(
            report,
            DiagnosticCategory.SECURITY,
            _("Zablokowano odwołanie poza publikację."),
            "zablokowany_url",
            safe_source_url(value),
            None,
            requester,
        )
        return None
    if not parsed.path:
        return generation.resource_url(base_path, parsed.fragment or None)
    target = _resolved_path(value, base_path)
    if target is None:
        _report(
            report,
            DiagnosticCategory.SECURITY,
            _("Zablokowano niebezpieczną ścieżkę zasobu."),
            "niebezpieczna_sciezka",
            value,
            None,
            requester,
        )
        return None
    if not generation.resource_provider.exists(target):
        _report(
            report,
            DiagnosticCategory.BOOK_ERROR,
            _("Brak zasobu wskazanego przez publikację."),
            "brak_zasobu",
            value,
            target,
            requester,
        )
        return None
    return generation.resource_url(target, parsed.fragment or None)


def safe_source_url(value: str) -> str:
    """Redaguje lokalne ścieżki, dane i sekrety query z diagnostyki."""
    parsed = urlsplit(value)
    if parsed.scheme in {"file", "data"}:
        return f"{parsed.scheme}:[ukryto]"
    if parsed.scheme:
        host = parsed.hostname or ""
        return f"{parsed.scheme}://{host}" if host else f"{parsed.scheme}:[ukryto]"
    return value[:500]


def _resolved_path(source_url: str, base_path: str) -> str | None:
    """Zwraca bezpieczną ścieżkę archiwum albo None."""
    parsed = urlsplit(source_url.strip())
    try:
        decoded = unquote(parsed.path, errors="strict")
        base_dir = (
            base_path.rstrip("/") if base_path.endswith("/") else posixpath.dirname(base_path)
        )
        combined = posixpath.normpath(posixpath.join(base_dir, decoded))
        return normalize_internal_path(combined)
    except (UnicodeDecodeError, UnsafePreviewPathError):
        return None


def _element_base(element: etree._Element, requester: str) -> str:
    """Uwzględnia dziedziczone xml:base bez dopuszczania wyjścia z publikacji."""
    bases = [
        ancestor.get(_XML_BASE)
        for ancestor in [*reversed(list(element.iterancestors())), element]
        if ancestor.get(_XML_BASE)
    ]
    current = requester
    for value in bases:
        resolved = _resolved_path(value or "", current)
        if resolved is not None:
            current = resolved + "/" if (value or "").endswith("/") else resolved
    return current


def _remove_xml_bases(root: etree._Element) -> None:
    """Usuwa xml:base dopiero po rozwiązaniu odwołań wszystkich potomków."""
    for element in root.iter():
        if _XML_BASE in element.attrib:
            del element.attrib[_XML_BASE]


def _report(
    report: DiagnosticSink | None,
    category: DiagnosticCategory,
    message: str,
    problem_kind: str,
    source_url: str,
    resolved_path: str | None,
    requester: str,
) -> None:
    """Emituje diagnostykę bez ścieżek systemowych i danych publikacji."""
    if report is not None:
        report(
            DiagnosticEvent(
                category=category,
                message=message,
                problem_kind=problem_kind,
                source_url=source_url,
                internal_path=resolved_path,
                requester=requester,
            )
        )
