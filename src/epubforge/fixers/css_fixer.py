"""Czyszczenie i normalizacja CSS w plikach EPUB przez tinycss2."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, cast

import tinycss2
from lxml import etree

from epubforge.core import Epub, ManifestItem
from epubforge.core._xml_safe import parse_untrusted
from epubforge.core.publication_href import read_publication_member
from epubforge.fixers._fontutil import FONT_MEDIA_TYPES as _FONT_MEDIA_TYPES
from epubforge.fixers._fontutil import FONT_SUFFIXES as _FONT_SUFFIXES
from epubforge.fixers._fontutil import font_files as _font_files
from epubforge.fixers._fontutil import href_suffix as _href_suffix
from epubforge.fixers._fontutil import manifest_path as _manifest_path

JustifyMode = Literal["keep", "left"]

_CSS_MEDIA_TYPES = {"text/css"}
_COLOR_PROPERTIES = {"color", "background", "background-color"}
_FONT_PROPERTIES = {"font-family"}
_RESET_RULE = "html, body { margin: 0; padding: 0; }"
_HEADER_HYPHEN_RULE = "h1, h2, h3 { hyphens: none; }"
_OPF_NS = "http://www.idpf.org/2007/opf"


@dataclass
class CssFixOptions:
    """Opcje normalizacji CSS w EPUB.

    Attributes:
        remove_colors: usuń deklaracje ``color``, ``background`` i ``background-color``.
        remove_fonts: usuń ``@font-face``, ``font-family`` i pliki fontów z EPUB-a.
        inject_reset: dodaj minimalny reset ``margin: 0; padding: 0``.
        replace_justify: ``left`` zamienia ``text-align: justify`` na ``left``.
        inject_book_margin_px: dodaj lub zaktualizuj ``@page { margin: Npx }``.
        skip_hyphenation_headers: dodaj regułę blokującą hyphenację nagłówków.
    """

    remove_colors: bool = False
    remove_fonts: bool = False
    inject_reset: bool = True
    replace_justify: JustifyMode = "keep"
    inject_book_margin_px: int | None = None
    skip_hyphenation_headers: bool = True


def fix_css(epub: Epub, options: CssFixOptions) -> None:
    """Aplikuje wybrane poprawki CSS do wszystkich arkuszy w otwartym EPUB-ie."""
    for item in _css_items(epub):
        internal_path = _manifest_path(epub, item)
        original = read_publication_member(epub, internal_path)
        css = original.decode("utf-8", errors="replace")

        if options.remove_colors:
            css = _remove_colors(css)
        if options.remove_fonts:
            css = _remove_fonts(epub, css)
        if options.inject_reset:
            css = _inject_reset(css)
        if options.replace_justify == "left":
            css = _replace_justify(css)
        if options.inject_book_margin_px is not None:
            css = _inject_book_margin(css, options.inject_book_margin_px)
        if options.skip_hyphenation_headers:
            css = _skip_hyphenation_headers(css)

        updated = css.encode()
        if updated != original:
            epub.write_file(internal_path, updated)


def _remove_colors(css: str) -> str:
    """Usuwa deklaracje koloru i tła, nie ruszając nieznanych reguł."""
    return _rewrite_declarations(
        css,
        remove=lambda declaration: _declaration_name(declaration) in _COLOR_PROPERTIES,
    )


def _remove_fonts(epub: Epub, css: str) -> str:
    """Usuwa reguły/deklaracje fontów oraz fizyczne pliki fontów z EPUB-a."""
    for internal_path in _font_files(epub):
        epub.delete_file(internal_path)
    _remove_font_manifest_items(epub)

    rules = _parse_stylesheet(css)
    kept_rules: list[Any] = []
    for rule in rules:
        if _node_type(rule) == "at-rule" and _at_keyword(rule) == "font-face":
            continue
        kept_rules.append(rule)
    css_without_font_face = _serialize(kept_rules)
    return _rewrite_declarations(
        css_without_font_face,
        remove=lambda declaration: _declaration_name(declaration) in _FONT_PROPERTIES,
    )


def _inject_reset(css: str) -> str:
    """Dodaje minimalny reset CSS, idempotentnie."""
    if "margin: 0" in css and "padding: 0" in css:
        return css
    return _prepend_rule(css, _RESET_RULE)


def _replace_justify(css: str) -> str:
    """Zamienia ``text-align: justify`` na ``text-align: left``."""

    def transform(declaration: Any) -> Any:
        if _declaration_name(declaration) != "text-align":
            return declaration
        value = _declaration_value(declaration).strip().lower()
        if value == "justify":
            declaration.value = _parse_component_values("left")
        return declaration

    return _rewrite_declarations(css, transform=transform)


def _inject_book_margin(css: str, px: int) -> str:
    """Dodaje lub aktualizuje ``@page { margin: Npx }``."""
    rules = _parse_stylesheet(css)
    margin_value = f"{px}px"
    found_page = False
    for rule in rules:
        if _node_type(rule) != "at-rule" or _at_keyword(rule) != "page":
            continue
        found_page = True
        declarations = _parse_declarations(getattr(rule, "content", None) or [])
        rule.content = _declarations_to_content(
            _upsert_declaration(declarations, "margin", margin_value)
        )

    if not found_page:
        rules.append(_parse_stylesheet(f"@page {{ margin: {margin_value}; }}")[0])
    return _serialize(rules)


def _skip_hyphenation_headers(css: str) -> str:
    """Dodaje regułę wyłączającą hyphenację w nagłówkach, idempotentnie."""
    if "h1, h2, h3" in css and "hyphens: none" in css:
        return css
    return _append_rule(css, _HEADER_HYPHEN_RULE)


def _rewrite_declarations(
    css: str,
    *,
    remove: Callable[[Any], bool] | None = None,
    transform: Callable[[Any], Any] | None = None,
) -> str:
    """Przepisuje deklaracje w regułach kwalifikowanych, zachowując resztę."""
    rules = _parse_stylesheet(css)
    for rule in rules:
        if _node_type(rule) != "qualified-rule":
            continue
        declarations = _parse_declarations(getattr(rule, "content", None) or [])
        updated: list[Any] = []
        for node in declarations:
            if _node_type(node) == "declaration":
                if remove is not None and remove(node):
                    continue
                if transform is not None:
                    node = transform(node)
            updated.append(node)
        rule.content = _declarations_to_content(updated)
    return _serialize(rules)


def _css_items(epub: Epub) -> list[ManifestItem]:
    """Zwraca wpisy manifestu wskazujące arkusze CSS."""
    return [
        item
        for item in epub.manifest
        if item.media_type in _CSS_MEDIA_TYPES or _href_suffix(item.href) == ".css"
    ]


def _remove_font_manifest_items(epub: Epub) -> None:
    """Usuwa z OPF wpisy manifestu prowadzące do plików fontów."""
    root = parse_untrusted(epub.read_file(epub.opf_path))
    manifest = root.find(f"{{{_OPF_NS}}}manifest")
    if manifest is None:
        return
    changed = False
    for item in list(manifest):
        href = item.get("href")
        media_type = item.get("media-type")
        if href is None or media_type is None:
            continue
        if media_type in _FONT_MEDIA_TYPES or _href_suffix(href) in _FONT_SUFFIXES:
            manifest.remove(item)
            changed = True
    if changed:
        epub.write_file(epub.opf_path, etree.tostring(root, encoding="utf-8", xml_declaration=True))


def _upsert_declaration(declarations: list[Any], name: str, value: str) -> list[Any]:
    """Aktualizuje deklarację lub dodaje ją na końcu listy."""
    found = False
    updated: list[Any] = []
    for node in declarations:
        if _node_type(node) == "declaration" and _declaration_name(node) == name:
            node.value = _parse_component_values(value)
            found = True
        updated.append(node)
    if not found:
        updated.extend(_parse_declarations(_parse_component_values(f"{name}: {value};")))
    return updated


def _prepend_rule(css: str, rule: str) -> str:
    """Dodaje regułę na początku arkusza."""
    rules = _parse_stylesheet(css)
    return _serialize([*_parse_stylesheet(rule), *rules])


def _append_rule(css: str, rule: str) -> str:
    """Dodaje regułę na końcu arkusza."""
    rules = _parse_stylesheet(css)
    return _serialize([*rules, *_parse_stylesheet(rule)])


def _parse_stylesheet(css: str) -> list[Any]:
    """Parsuje CSS do reguł tinycss2."""
    return cast(list[Any], tinycss2.parse_stylesheet(css, skip_whitespace=True))


def _parse_declarations(content: list[Any]) -> list[Any]:
    """Parsuje content reguły do deklaracji tinycss2."""
    return cast(list[Any], tinycss2.parse_declaration_list(content, skip_whitespace=True))


def _parse_component_values(css: str) -> list[Any]:
    """Parsuje fragment CSS do tokenów component value."""
    return cast(list[Any], tinycss2.parse_component_value_list(css))


def _declarations_to_content(declarations: list[Any]) -> list[Any]:
    """Serializuje deklaracje i parsuje je z powrotem jako content reguły."""
    return _parse_component_values(_serialize(declarations))


def _serialize(nodes: list[Any]) -> str:
    """Serializuje węzły tinycss2."""
    return cast(str, tinycss2.serialize(nodes))


def _node_type(node: Any) -> str:
    """Zwraca typ węzła tinycss2."""
    return str(getattr(node, "type", ""))


def _at_keyword(node: Any) -> str:
    """Zwraca nazwę at-rule małymi literami."""
    return str(getattr(node, "at_keyword", "")).lower()


def _declaration_name(node: Any) -> str:
    """Zwraca nazwę deklaracji małymi literami."""
    lower = getattr(node, "lower_name", None)
    if isinstance(lower, str):
        return lower
    return str(getattr(node, "name", "")).lower()


def _declaration_value(node: Any) -> str:
    """Serializuje wartość deklaracji."""
    return _serialize(cast(list[Any], getattr(node, "value", [])))
