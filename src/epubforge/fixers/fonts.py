"""Subsetting fontów w EPUB — przycinanie do faktycznie użytych glifów.

Zamiast usuwać fonty (jak ``css_fixer`` z ``remove_fonts``), ten fixer przycina
je do znaków użytych w treści, zwykle oszczędzając 70–90 % rozmiaru pliku.
``fonttools`` jest **opcjonalną** zależnością (extra ``[fonts]``) importowaną
leniwie — bez niej operacja zgłasza czytelny błąd instalacji.

⚠️ **Licencje**: część licencji fontów zabrania modyfikacji. Przed subsetem
sprawdź licencję fontu — narzędzie nie czyta jej automatycznie (ostrzeżenie w
GUI/CLI).

Pułapki (zob. ROADMAP Etap 24):
* zbiór znaków = WSZYSTKIE dokumenty spine + literały CSS + **stały zestaw
  bezpieczeństwa** (ASCII, polskie znaki, interpunkcja typograficzna oraz
  ``U+00AD``/``U+00A0``) — inaczej efekty hyphenacji/typografii by się nie
  renderowały;
* format zachowany (ttf→ttf, otf→otf, woff→woff, woff2→woff2);
* ``@font-face`` z ``unicode-range`` → font pomijany (bezpieczniej);
* WOFF2 wymaga ``brotli`` — bez niego plik pomijany z ostrzeżeniem (nie wyjątek);
* zapis tylko gdy wynik mniejszy.
"""

from __future__ import annotations

import importlib.util
import io
import logging
import posixpath
from dataclasses import dataclass, field
from typing import Any

import tinycss2

from epubforge.core import Epub
from epubforge.core._xml_safe import parse_untrusted_document
from epubforge.core.exceptions import InvalidPublicationHrefError
from epubforge.core.publication_href import resolve_from_directory
from epubforge.fixers._fontutil import font_files, href_suffix, manifest_path
from epubforge.i18n import _

logger = logging.getLogger(__name__)

_CSS_MEDIA_TYPES = {"text/css"}

# Interpunkcja typograficzna wstawiana przez fixery typografii (Etap 16) —
# musi zostać w foncie, żeby tekst po naprawie się renderował.
_TYPOGRAPHIC = "„”“‚’‘«»—–…•·"
# Polskie znaki diakrytyczne (małe i wielkie).
_POLISH = "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"


class FontSubsetError(RuntimeError):
    """Błąd subsettingu fontów (np. brak biblioteki fonttools)."""


@dataclass
class FontSubsetOptions:
    """Opcje subsettingu fontów.

    Attributes:
        extra_chars: dodatkowe znaki, które zawsze zachować w foncie
            (poza treścią i zestawem bezpieczeństwa).
    """

    extra_chars: str = ""


@dataclass(frozen=True)
class FontResult:
    """Wynik subsettingu jednego pliku fontu."""

    internal_path: str
    size_before: int
    size_after: int
    changed: bool
    note: str = ""


@dataclass
class FontReport:
    """Zbiorczy raport subsettingu fontów."""

    results: list[FontResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def record(self, result: FontResult) -> None:
        """Dodaje wynik pojedynczego fontu do raportu."""
        self.results.append(result)

    @property
    def total_before(self) -> int:
        """Sumaryczny rozmiar fontów przed subsetem."""
        return sum(result.size_before for result in self.results)

    @property
    def total_after(self) -> int:
        """Sumaryczny rozmiar fontów po subsecie."""
        return sum(result.size_after for result in self.results)

    @property
    def saved_bytes(self) -> int:
        """Liczba zaoszczędzonych bajtów (≥ 0)."""
        return self.total_before - self.total_after

    @property
    def saved_percent(self) -> float:
        """Procent oszczędności względem rozmiaru wejściowego (0 gdy brak danych)."""
        before = self.total_before
        if before <= 0:
            return 0.0
        return round(self.saved_bytes / before * 100, 1)

    @property
    def changed_files(self) -> list[str]:
        """Ścieżki fontów faktycznie przyciętych."""
        return [result.internal_path for result in self.results if result.changed]


def subset_fonts(epub: Epub, options: FontSubsetOptions) -> FontReport:
    """Przycina fonty w otwartym EPUB-ie do znaków użytych w treści.

    Args:
        epub: otwarty plik EPUB (zmiany trafiają do bufora ``write_file``).
        options: parametry subsettingu.

    Returns:
        :class:`FontReport` z rozmiarami przed/po dla każdego fontu oraz
        ostrzeżeniami (np. pominięte WOFF2 bez brotli, fonty z ``unicode-range``).

    Raises:
        FontSubsetError: gdy ``fonttools`` nie jest zainstalowane.
    """
    subset_mod, ttlib = _load_fonttools()  # wczesny, czytelny błąd gdy brak fonttools
    report = FontReport()

    codepoints = _wanted_codepoints(epub, options, report)
    range_fonts = _fonts_with_unicode_range(epub, report)
    brotli_available = importlib.util.find_spec("brotli") is not None

    for path in font_files(epub):
        try:
            original = epub.read_file(path)
        except KeyError:
            note = _("brak zasobu publikacji w archiwum")
            report.warnings.append(f"{path}: {note}")
            report.record(FontResult(path, 0, 0, changed=False, note=note))
            continue
        note = _skip_reason(path, range_fonts, brotli_available, report)
        if note:
            report.record(FontResult(path, len(original), len(original), changed=False, note=note))
            continue
        subsetted = _subset_one(subset_mod, ttlib, original, codepoints)
        if subsetted is not None and len(subsetted) < len(original):
            epub.write_file(path, subsetted)
            report.record(FontResult(path, len(original), len(subsetted), changed=True))
        else:
            skip_note = "" if subsetted is not None else _("nie udało się odczytać fontu")
            report.record(
                FontResult(path, len(original), len(original), changed=False, note=skip_note)
            )
    return report


def _skip_reason(
    path: str, range_fonts: set[str], brotli_available: bool, report: FontReport
) -> str:
    """Zwraca powód pominięcia fontu (lub pusty łańcuch, gdy można go przyciąć)."""
    if path in range_fonts:
        return _("pominięto: @font-face z unicode-range")
    if href_suffix(path) == ".woff2" and not brotli_available:
        report.warnings.append(
            _('{path}: WOFF2 wymaga brotli (pip install "epubforge[fonts]") — pominięto').format(
                path=path
            )
        )
        return _("pominięto WOFF2: brak brotli")
    return ""


def _load_fonttools() -> tuple[Any, Any]:
    """Zwraca moduły ``fontTools.subset`` i ``fontTools.ttLib`` albo czytelny błąd."""
    try:
        from fontTools import subset, ttLib
    except ImportError as exc:  # pragma: no cover - zależne od środowiska
        raise FontSubsetError(
            _('Subsetting fontów wymaga fonttools. Zainstaluj: pip install "epubforge[fonts]"')
        ) from exc
    return subset, ttLib


def _subset_one(subset_mod: Any, ttlib: Any, data: bytes, codepoints: set[int]) -> bytes | None:
    """Przycina jeden font do ``codepoints``, zachowując format. ``None`` przy błędzie."""
    try:
        font = ttlib.TTFont(io.BytesIO(data), fontNumber=0, lazy=True)
        flavor = font.flavor  # None (ttf/otf) / "woff" / "woff2" — zachowujemy format
        subsetter = subset_mod.Subsetter()
        subsetter.populate(unicodes=sorted(codepoints))
        subsetter.subset(font)
        buffer = io.BytesIO()
        font.flavor = flavor
        font.save(buffer)
        return buffer.getvalue()
    except Exception:  # uszkodzony font nie może wywalić całego batcha
        logger.exception("Nie udało się przyciąć fontu (pomijam)")
        return None


# ── Zbiór znaków ──────────────────────────────────────────────────────────────


def _wanted_codepoints(epub: Epub, options: FontSubsetOptions, report: FontReport) -> set[int]:
    """Buduje zbiór codepointów: treść + literały CSS + zestaw bezpieczeństwa."""
    chars = _safety_charset() | set(options.extra_chars)
    chars |= _content_chars(epub, report)
    return {ord(char) for char in chars}


def _safety_charset() -> set[str]:
    """Stały zestaw znaków zawsze zachowywanych (ASCII, PL, typografia, AD/A0)."""
    chars = {chr(code) for code in range(0x20, 0x7F)}  # ASCII drukowalne
    chars.update(_POLISH)
    chars.update(_TYPOGRAPHIC)
    chars.add("­")  # miękki dywiz (efekt hyphenacji)
    chars.add(" ")  # twarda spacja (efekt typografii)
    return chars


def _content_chars(epub: Epub, report: FontReport) -> set[str]:
    """Zbiera znaki ze wszystkich dokumentów spine oraz literałów CSS."""
    chars: set[str] = set()
    for path in _spine_doc_paths(epub):
        try:
            data = epub.read_file(path)
        except KeyError:
            report.warnings.append(_("{path}: brak dokumentu spine w archiwum").format(path=path))
            continue
        try:
            root, _doctype = parse_untrusted_document(data)
        except ValueError:
            continue
        for text in root.itertext():
            if isinstance(text, str):  # itertext() typuje str | bytes; glify liczymy z tekstu
                chars.update(text)
    for path in _css_paths(epub):
        try:
            chars |= _css_string_chars(epub.read_file(path))
        except KeyError:
            report.warnings.append(_("{path}: brak arkusza CSS w archiwum").format(path=path))
    return chars


def _spine_doc_paths(epub: Epub) -> list[str]:
    """Zwraca wewnętrzne ścieżki dokumentów w kolejności spine."""
    by_id = {item.id: item for item in epub.manifest}
    paths: list[str] = []
    for idref in epub.spine:
        item = by_id.get(idref)
        if item is not None:
            try:
                paths.append(manifest_path(epub, item))
            except InvalidPublicationHrefError:
                continue
    return paths


def _css_paths(epub: Epub) -> list[str]:
    """Zwraca wewnętrzne ścieżki arkuszy CSS."""
    result: list[str] = []
    for item in epub.manifest:
        if item.media_type in _CSS_MEDIA_TYPES or href_suffix(item.href) == ".css":
            try:
                result.append(manifest_path(epub, item))
            except InvalidPublicationHrefError:
                continue
    return result


def _css_string_chars(data: bytes) -> set[str]:
    """Zbiera znaki ze wszystkich literałów tekstowych CSS (nadzbiór wartości ``content``)."""
    css = data.decode("utf-8", "replace")
    chars: set[str] = set()
    _collect_string_tokens(tinycss2.parse_component_value_list(css), chars)
    return chars


def _collect_string_tokens(nodes: list[Any], chars: set[str]) -> None:
    """Rekurencyjnie zbiera znaki z tokenów tekstowych (także w blokach ``{}``)."""
    for node in nodes:
        if getattr(node, "type", "") == "string":
            chars.update(node.value)
        content = getattr(node, "content", None)
        if content:
            _collect_string_tokens(content, chars)


# ── unicode-range (fonty do pominięcia) ──────────────────────────────────────


def _fonts_with_unicode_range(epub: Epub, report: FontReport) -> set[str]:
    """Zwraca ścieżki fontów, których ``@font-face`` deklaruje ``unicode-range``."""
    skip: set[str] = set()
    for css_path in _css_paths(epub):
        try:
            css = epub.read_file(css_path).decode("utf-8", "replace")
        except KeyError:
            report.warnings.append(_("{path}: brak arkusza CSS w archiwum").format(path=css_path))
            continue
        base = posixpath.dirname(css_path)
        for rule in tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True):
            if getattr(rule, "type", "") != "at-rule" or rule.lower_at_keyword != "font-face":
                continue
            if rule.content is None:
                continue
            _collect_range_srcs(rule.content, base, skip)
    return skip


def _collect_range_srcs(content: list[Any], base: str, skip: set[str]) -> None:
    """Gdy ``@font-face`` ma ``unicode-range``, dodaje ścieżki z jego ``src`` do ``skip``."""
    declarations = tinycss2.parse_declaration_list(
        content, skip_comments=True, skip_whitespace=True
    )
    decls = [node for node in declarations if getattr(node, "type", "") == "declaration"]
    if not any(decl.lower_name == "unicode-range" for decl in decls):
        return
    for decl in decls:
        if decl.lower_name == "src":
            for url in _urls_in(decl.value):
                resolved = _resolve(base, url)
                if resolved is not None:
                    skip.add(resolved)


def _urls_in(tokens: list[Any]) -> list[str]:
    """Wyciąga adresy z tokenów wartości ``src`` (``url(...)`` i ``url("...")``)."""
    urls: list[str] = []
    for token in tokens:
        token_type = getattr(token, "type", "")
        if token_type == "url":
            urls.append(token.value)
        elif token_type == "function" and token.lower_name == "url":
            for arg in token.arguments:
                if getattr(arg, "type", "") == "string":
                    urls.append(arg.value)
    return urls


def _resolve(base: str, url: str) -> str | None:
    """Rozwiązuje adres z CSS względem katalogu arkusza na ścieżkę w archiwum."""
    try:
        return resolve_from_directory(base, url)
    except InvalidPublicationHrefError:
        return None
