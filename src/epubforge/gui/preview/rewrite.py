"""Przepisywanie odwołań publikacji do izolowanego schematu podglądu."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast
from urllib.parse import urlsplit

import tinycss2
from lxml import etree
from tinycss2 import ast as tinycss_ast

from epubforge.core._xml_safe import parse_untrusted_document, serialize_document
from epubforge.gui.preview.backend import DiagnosticCategory, DiagnosticEvent
from epubforge.gui.preview.dom_mapping import assign_render_node_ids
from epubforge.gui.preview.paths import resolve_publication_path
from epubforge.gui.preview.sanitize import sanitize_xhtml
from epubforge.gui.preview.session import PreviewGeneration
from epubforge.gui.preview.srcset import parse_srcset
from epubforge.i18n import _

DiagnosticSink = Callable[[DiagnosticEvent], None]
_XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
_URL_ATTRIBUTES = frozenset(
    {
        "href",
        "src",
        "poster",
        "data",
        "action",
        "formaction",
        "background",
        "cite",
        "ping",
        "manifest",
        "usemap",
        "longdesc",
        "profile",
        "archive",
        "codebase",
    }
)
_SVG_CSS_URL_ATTRIBUTES = frozenset(
    {
        "clip-path",
        "cursor",
        "fill",
        "filter",
        "marker",
        "marker-end",
        "marker-mid",
        "marker-start",
        "mask",
        "stroke",
    }
)


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
        tag = cast(object, element.tag)
        if not isinstance(tag, str):
            # ``resolve_entities=False`` celowo zachowuje bezpieczne referencje
            # encji jako węzły ``_Entity``. Nie są elementami DOM i nie wolno
            # przekazywać ich do ``QName`` (częste w starszych EPUB-ach: &nbsp;).
            continue
        base = _element_base(element, requester)
        for attribute in list(element.attrib):
            local = etree.QName(attribute).localname.lower()
            if local in _URL_ATTRIBUTES or attribute == _XLINK_HREF:
                original = cast(str, element.attrib[attribute])
                rewritten = resolve_reference(original, base, generation, requester, report)
                if rewritten is None:
                    del element.attrib[attribute]
                else:
                    element.attrib[attribute] = rewritten
                    if local == "href" and etree.QName(element.tag).localname.lower() == "link":
                        target = _resolved_path(original, base)
                        if target is not None:
                            element.set("data-epubforge-path", target)
            elif local == "srcset":
                rewritten_srcset = rewrite_srcset(
                    cast(str, element.attrib[attribute]), generation, base, requester, report
                )
                if rewritten_srcset is None:
                    del element.attrib[attribute]
                else:
                    element.attrib[attribute] = rewritten_srcset
            elif local == "style":
                element.attrib[attribute] = rewrite_css_text(
                    cast(str, element.attrib[attribute]),
                    generation,
                    base,
                    requester,
                    report,
                    stylesheet=False,
                )
            elif local in _SVG_CSS_URL_ATTRIBUTES:
                element.attrib[attribute] = rewrite_css_value(
                    cast(str, element.attrib[attribute]), generation, base, requester, report
                )
        if etree.QName(tag).localname.lower() == "style" and element.text:
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
    root_tag = cast(object, root.tag)
    if isinstance(root_tag, str) and etree.QName(root_tag).localname.lower() in {
        "script",
        "foreignobject",
    }:
        namespace = etree.QName(root_tag).namespace
        root = etree.Element(f"{{{namespace}}}svg" if namespace else "svg")
        doctype = ""
    for element in list(root.iter()):
        tag = cast(object, element.tag)
        if not isinstance(tag, str):
            continue
        local_name = etree.QName(tag).localname.lower()
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
                if rewritten is None:
                    del element.attrib[attribute]
                else:
                    element.attrib[attribute] = rewritten
            elif local == "srcset":
                rewritten_srcset = rewrite_srcset(
                    cast(str, element.attrib[attribute]), generation, base, requester, report
                )
                if rewritten_srcset is None:
                    del element.attrib[attribute]
                else:
                    element.attrib[attribute] = rewritten_srcset
            elif local == "style":
                element.attrib[attribute] = rewrite_css_text(
                    cast(str, element.attrib[attribute]),
                    generation,
                    base,
                    requester,
                    report,
                    stylesheet=False,
                )
            elif local in _SVG_CSS_URL_ATTRIBUTES:
                element.attrib[attribute] = rewrite_css_value(
                    cast(str, element.attrib[attribute]), generation, base, requester, report
                )
        if local_name == "style" and element.text:
            element.text = rewrite_css_text(element.text, generation, base, requester, report)
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
    *,
    stylesheet: bool = True,
) -> str:
    """Wersjonuje CSS przez tinycss2; blokowane URL-e nie przeżywają w wyniku."""
    try:
        if stylesheet:
            return _rewrite_stylesheet(text, generation, base_path, requester, report)
        return _rewrite_declarations(text, generation, base_path, requester, report)
    except (TypeError, ValueError):
        return ""


def rewrite_css_value(
    text: str,
    generation: PreviewGeneration,
    base_path: str,
    requester: str,
    report: DiagnosticSink | None = None,
) -> str:
    """Przepisuje ``url()`` w pojedynczej wartości CSS, np. atrybucie SVG."""
    try:
        tokens = tinycss2.parse_component_value_list(text, skip_comments=False)
        tokens = _rewrite_css_tokens(tokens, generation, base_path, requester, report)
        return cast(str, tinycss2.serialize(tokens))
    except (TypeError, ValueError):
        return ""


def _rewrite_stylesheet(
    text: str,
    generation: PreviewGeneration,
    base_path: str,
    requester: str,
    report: DiagnosticSink | None,
) -> str:
    """Filtruje reguły arkusza i usuwa niedozwolone ``@import``."""
    rules = tinycss2.parse_stylesheet(text, skip_comments=False, skip_whitespace=False)
    clean_rules: list[Any] = []
    for rule in rules:
        if rule.type == "error":
            continue
        if rule.type == "at-rule" and getattr(rule, "lower_at_keyword", "") == "import":
            if not _rewrite_import(rule, generation, base_path, requester, report):
                continue
            clean_rules.append(rule)
            continue
        prelude = getattr(rule, "prelude", None)
        if prelude is not None:
            prelude[:] = _rewrite_css_tokens(prelude, generation, base_path, requester, report)
        content = getattr(rule, "content", None)
        if content is not None:
            content[:] = _rewrite_css_tokens(content, generation, base_path, requester, report)
        clean_rules.append(rule)
    return cast(str, tinycss2.serialize(clean_rules))


def _rewrite_declarations(
    text: str,
    generation: PreviewGeneration,
    base_path: str,
    requester: str,
    report: DiagnosticSink | None,
) -> str:
    """Przepisuje URL-e w atrybucie ``style`` bez traktowania go jak arkusza."""
    declarations = tinycss2.parse_declaration_list(text, skip_comments=False, skip_whitespace=False)
    clean_declarations: list[Any] = []
    for declaration in declarations:
        if declaration.type == "error":
            continue
        value = getattr(declaration, "value", None)
        if value is not None:
            value[:] = _rewrite_css_tokens(value, generation, base_path, requester, report)
        clean_declarations.append(declaration)
    return cast(str, tinycss2.serialize(clean_declarations))


def _rewrite_import(
    rule: Any,
    generation: PreviewGeneration,
    base_path: str,
    requester: str,
    report: DiagnosticSink | None,
) -> bool:
    """Przepisuje pierwszy URL ``@import`` albo odrzuca całą aktywną regułę."""
    for index, token in enumerate(rule.prelude):
        if token.type in {"whitespace", "comment"}:
            continue
        source = _css_url_value(token)
        if source is None:
            return False
        resolved = resolve_reference(source, base_path, generation, requester, report)
        if resolved is None:
            return False
        rule.prelude[index] = _css_url_token(token, resolved)
        return True
    return False


def _rewrite_css_tokens(
    tokens: list[Any],
    generation: PreviewGeneration,
    base_path: str,
    requester: str,
    report: DiagnosticSink | None,
) -> list[Any]:
    """Przepisuje rekurencyjnie URLToken/``url()``; błędne URL-e neutralizuje."""
    rewritten: list[Any] = []
    for token in tokens:
        if token.type == "url" or (
            token.type == "function" and getattr(token, "lower_name", "") == "url"
        ):
            source = _css_url_value(token)
            resolved = (
                resolve_reference(source, base_path, generation, requester, report)
                if source is not None
                else None
            )
            rewritten.append(_css_url_token(token, resolved or ""))
            continue
        if token.type == "error":
            continue
        arguments = getattr(token, "arguments", None)
        if arguments is not None:
            arguments[:] = _rewrite_css_tokens(arguments, generation, base_path, requester, report)
        content = getattr(token, "content", None)
        if content is not None:
            content[:] = _rewrite_css_tokens(content, generation, base_path, requester, report)
        rewritten.append(token)
    return rewritten


def _css_url_value(token: Any) -> str | None:
    """Zwraca URL z tokenu tinycss2 tylko dla jednoznacznej składni."""
    if token.type in {"url", "string"}:
        return cast(str, token.value)
    if token.type != "function" or getattr(token, "lower_name", "") != "url":
        return None
    values = [
        argument for argument in token.arguments if argument.type not in {"whitespace", "comment"}
    ]
    if len(values) != 1 or values[0].type != "string":
        return None
    return cast(str, values[0].value)


def _css_url_token(original: Any, value: str) -> Any:
    """Buduje bezpiecznie cytowany token URL, zachowując formę stringu w ``@import``."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\a ")
    if original.type == "string":
        return tinycss_ast.StringToken(
            original.source_line, original.source_column, value, f'"{escaped}"'
        )
    return tinycss_ast.URLToken(
        original.source_line, original.source_column, value, f'url("{escaped}")'
    )


def resolve_reference(
    source_url: str,
    base_path: str,
    generation: PreviewGeneration,
    requester: str,
    report: DiagnosticSink | None = None,
) -> str | None:
    """Rozwiązuje względny URL wyłącznie wewnątrz bieżącej publikacji."""
    value = source_url.strip()
    try:
        parsed = urlsplit(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.scheme or parsed.netloc or parsed.query:
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


def rewrite_srcset(
    source: str,
    generation: PreviewGeneration,
    base_path: str,
    requester: str,
    report: DiagnosticSink | None = None,
) -> str | None:
    """Przepisuje osobno każdy poprawny kandydat ``srcset`` i odrzuca resztę."""
    candidates = parse_srcset(source)
    if candidates is None:
        return None
    rewritten: list[str] = []
    for url, descriptor in candidates:
        target = resolve_reference(url, base_path, generation, requester, report)
        if target is not None:
            rewritten.append(f"{target} {descriptor}" if descriptor else target)
    return ", ".join(rewritten) or None


def safe_source_url(value: str) -> str:
    """Redaguje lokalne ścieżki, dane i sekrety query z diagnostyki."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value[:500]
    if parsed.scheme in {"file", "data"}:
        return f"{parsed.scheme}:[ukryto]"
    if parsed.scheme:
        host = parsed.hostname or ""
        return f"{parsed.scheme}://{host}" if host else f"{parsed.scheme}:[ukryto]"
    return value[:500]


def _resolved_path(source_url: str, base_path: str) -> str | None:
    """Zwraca bezpieczną ścieżkę archiwum albo None."""
    return resolve_publication_path(source_url, base_path)


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
