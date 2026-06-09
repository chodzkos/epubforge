"""Dzielenie wyrazów w plikach EPUB.

Dostępne są dwie metody:

* ``soft-hyphen`` — fizycznie wstawia znaki U+00AD w tekst.
* ``css`` — dodaje regułę ``hyphens: auto`` i zostawia tekst bez zmian.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast
from urllib.parse import unquote, urldefrag

import pyphen
from lxml import etree

from epubforge.core import Epub, ManifestItem

HyphenationMethod = Literal["soft-hyphen", "css"]

SOFT_HYPHEN = "\u00ad"
CSS_HYPHENATION_RULE = (
    "body { hyphens: auto; -webkit-hyphens: auto; -moz-hyphens: auto; "
    "hyphenate-limit-chars: 5 2 2; }"
)

_WORD_RE = re.compile(r"(?:[^\W\d_]|\u00ad)+", re.UNICODE)
_HTML_MEDIA_TYPES = {"application/xhtml+xml", "text/html"}
_CSS_MEDIA_TYPES = {"text/css"}
_SKIP_TAGS = {"code", "pre", "kbd", "samp", "var", "tt"}
_HEADER_TAGS = {"h1", "h2", "h3"}
_XHTML_NS = "http://www.w3.org/1999/xhtml"


@dataclass
class HyphenationOptions:
    """Opcje dzielenia wyrazów w EPUB.

    Ostrzeżenie: metoda ``soft-hyphen`` działa szeroko, także na starszych
    czytnikach Kindle, ale wstawia ukryte znaki w tekst. To może utrudnić
    wyszukiwanie słów i działanie słownika na czytniku, bo zaznaczone słowo
    zawiera wtedy U+00AD. Metoda ``css`` zostawia tekst czysty, ale ma słabsze
    wsparcie na wielu czytnikach e-ink. To świadomy kompromis wybierany przez
    użytkownika.

    Attributes:
        language: kod języka słownika Pyphen, np. ``pl``, ``en`` albo ``de``.
        method: ``soft-hyphen`` wstawia U+00AD; ``css`` dodaje regułę CSS.
        skip_headers: czy pomijać nagłówki ``h1``-``h3`` przy ``soft-hyphen``.
        skip_tags: tagi, których zawartość tekstowa nie jest modyfikowana.
        min_word_length: minimalna długość słowa do dzielenia.
    """

    language: str = "pl"
    method: HyphenationMethod = "soft-hyphen"
    skip_headers: bool = True
    skip_tags: set[str] = field(default_factory=lambda: set(_SKIP_TAGS))
    min_word_length: int = 5


def hyphenate(epub: Epub, options: HyphenationOptions) -> None:
    """Modyfikuje otwarty EPUB zgodnie z wybraną metodą dzielenia wyrazów.

    Funkcja zapisuje zmiany do bufora :class:`Epub` przez ``write_file``.
    Utrwalenie na dysku należy do wywołującego przez ``epub.save()``.
    """
    if options.method == "soft-hyphen":
        _apply_soft_hyphen(epub, options)
        return
    _apply_css_hyphenation(epub)


def _apply_soft_hyphen(epub: Epub, options: HyphenationOptions) -> None:
    """Wstawia U+00AD w tekstach dokumentów HTML/XHTML."""
    dictionary = pyphen.Pyphen(lang=options.language)
    for item in _html_items(epub):
        internal_path = _manifest_path(epub, item)
        original = epub.read_file(internal_path)
        updated = _hyphenate_document(original, dictionary, options)
        if updated != original:
            epub.write_file(internal_path, updated)


def _apply_css_hyphenation(epub: Epub) -> None:
    """Dodaje regułę CSS hyphenation do arkuszy lub osadza ją w HTML."""
    css_items = list(_css_items(epub))
    if css_items:
        for item in css_items:
            internal_path = _manifest_path(epub, item)
            original = epub.read_file(internal_path)
            updated = _inject_css_rule(original)
            if updated != original:
                epub.write_file(internal_path, updated)
        return

    for item in _html_items(epub):
        internal_path = _manifest_path(epub, item)
        original = epub.read_file(internal_path)
        updated = _inject_embedded_css(original)
        if updated != original:
            epub.write_file(internal_path, updated)


def _html_items(epub: Epub) -> list[ManifestItem]:
    """Zwraca wpisy manifestu wskazujące dokumenty HTML/XHTML."""
    return [
        item
        for item in epub.manifest
        if item.media_type in _HTML_MEDIA_TYPES or _href_suffix(item.href) in {".html", ".xhtml"}
    ]


def _css_items(epub: Epub) -> list[ManifestItem]:
    """Zwraca wpisy manifestu wskazujące arkusze CSS."""
    return [
        item
        for item in epub.manifest
        if item.media_type in _CSS_MEDIA_TYPES or _href_suffix(item.href) == ".css"
    ]


def _href_suffix(href: str) -> str:
    """Zwraca rozszerzenie href bez fragmentu URL."""
    path, _fragment = urldefrag(href)
    return Path(path).suffix.lower()


def _manifest_path(epub: Epub, item: ManifestItem) -> str:
    """Rozwiązuje ``manifest href`` względem katalogu OPF."""
    href, _fragment = urldefrag(item.href)
    href = unquote(href)
    if href.startswith("/"):
        return posixpath.normpath(href.lstrip("/"))
    base = epub.opf_dir()
    if not base:
        return posixpath.normpath(href)
    return posixpath.normpath(posixpath.join(base, href))


def _hyphenate_document(
    data: bytes,
    dictionary: pyphen.Pyphen,
    options: HyphenationOptions,
) -> bytes:
    """Parsuje dokument XML/XHTML i dzieli tekstowe węzły."""
    root = _parse_xml_document(data)
    _hyphenate_element(root, dictionary, options, blocked=False)
    return _serialize_xml(root, data)


def _hyphenate_element(
    element: etree._Element,
    dictionary: pyphen.Pyphen,
    options: HyphenationOptions,
    *,
    blocked: bool,
) -> None:
    """Rekurencyjnie dzieli tekst elementu, respektując pomijane tagi."""
    tag = _local_name(element)
    blocked_here = (
        blocked or tag in options.skip_tags or (options.skip_headers and tag in _HEADER_TAGS)
    )

    if element.text and not blocked_here:
        element.text = _hyphenate_text(element.text, dictionary, options.min_word_length)

    for child in element:
        if isinstance(child.tag, str):
            _hyphenate_element(child, dictionary, options, blocked=blocked_here)
        if child.tail and not blocked_here:
            child.tail = _hyphenate_text(child.tail, dictionary, options.min_word_length)


def _hyphenate_text(text: str, dictionary: pyphen.Pyphen, min_word_length: int) -> str:
    """Dzieli słowa w tekście, zostawiając już podzielone tokeny bez zmian."""

    def replace(match: re.Match[str]) -> str:
        word = match.group(0)
        if SOFT_HYPHEN in word or len(word) < min_word_length:
            return word
        return cast(str, dictionary.inserted(word, hyphen=SOFT_HYPHEN))

    return _WORD_RE.sub(replace, text)


def _inject_css_rule(data: bytes) -> bytes:
    """Dopisuje regułę hyphenation do arkusza CSS, idempotentnie."""
    css = data.decode("utf-8", errors="replace")
    if "hyphens: auto" in css:
        return data
    suffix = "\n" if css.endswith("\n") or not css else "\n\n"
    return f"{css}{suffix}{CSS_HYPHENATION_RULE}\n".encode()


def _inject_embedded_css(data: bytes) -> bytes:
    """Osadza regułę CSS w ``head`` dokumentu, gdy EPUB nie ma arkusza CSS."""
    root = _parse_xml_document(data)
    existing_styles = [element for element in root.iter() if _local_name(element) == "style"]
    for style in existing_styles:
        if isinstance(style.text, str) and "hyphens: auto" in style.text:
            return data

    head = root.find(f".//{{{_XHTML_NS}}}head")
    if head is None:
        head = root.find(".//head")
    if head is None:
        return data

    namespace = _element_namespace(head)
    tag = f"{{{namespace}}}style" if namespace else "style"
    style = etree.Element(tag)
    style.text = CSS_HYPHENATION_RULE
    head.append(style)
    return _serialize_xml(root, data)


def _parse_xml_document(data: bytes) -> etree._Element:
    """Parsuje XML/XHTML w trybie odzyskiwania drobnych nieścisłości."""
    parser = etree.XMLParser(resolve_entities=False, recover=True)
    return etree.fromstring(data, parser=parser)


def _serialize_xml(root: etree._Element, original: bytes) -> bytes:
    """Serializuje dokument, zachowując obecność deklaracji XML."""
    return etree.tostring(
        root,
        encoding="utf-8",
        xml_declaration=original.lstrip().startswith(b"<?xml"),
    )


def _local_name(element: etree._Element) -> str:
    """Zwraca lokalną nazwę tagu bez namespace."""
    return etree.QName(element.tag).localname.lower()


def _element_namespace(element: etree._Element) -> str:
    """Zwraca namespace elementu albo pusty łańcuch."""
    if not element.tag.startswith("{"):
        return ""
    return etree.QName(element.tag).namespace or ""
