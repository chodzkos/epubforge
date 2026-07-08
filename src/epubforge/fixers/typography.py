"""Fixer typografii tekstu w plikach EPUB (czysta logika, bez Qt).

Poprawia mikrotypografię dokumentów XHTML: cudzysłowy (dobierane wg języka),
pauzy/dywizy, wielokropek oraz twarde spacje po „sierotach" (samotne spójniki).
Wzorzec przejścia po drzewie ``text``/``tail`` jak w :mod:`hyphenator`; parsowanie
i serializacja przez utwardzony parser (Etap 15), z **zachowaniem DOCTYPE**.

Pułapki (patrz ROADMAP Etap 16):

* parowanie cudzysłowów jest **stanowe** — otwierający vs zamykający zależy od
  poprzedniego znaku; stan trzeba nieść przez granice tagów w obrębie akapitu
  (para może zacząć się w ``element.text`` i skończyć w ``child.tail``);
* iteracja z guardem ``isinstance(child.tag, str)`` — komentarze/PI lxml mają
  ``tag`` wywoływalny, nie łańcuch;
* ``code``/``pre`` (i zawsze ``style``/``script``) są nietykalne, atrybuty też;
* regexy tolerują ``U+00AD`` (miękki łącznik) wewnątrz słów.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urldefrag

from lxml import etree

from epubforge.core import Epub, ManifestItem
from epubforge.core._xml_safe import parse_untrusted_document, serialize_document

# ── Klucze reguł (stabilne — używane w raporcie, CLI i GUI) ──────────────────────
RULE_QUOTES = "fix_quotes"
RULE_DASHES = "fix_dashes"
RULE_ELLIPSIS = "fix_ellipsis"
RULE_NBSP_LETTERS = "nbsp_single_letters"
RULE_NBSP_NUMBERS = "nbsp_numbers_units"
_RULE_KEYS = (RULE_QUOTES, RULE_DASHES, RULE_ELLIPSIS, RULE_NBSP_LETTERS, RULE_NBSP_NUMBERS)

NBSP = " "
SOFT_HYPHEN = "­"

_HTML_MEDIA_TYPES = {"application/xhtml+xml", "text/html"}
_DEFAULT_SKIP_TAGS = {"code", "pre", "kbd", "samp", "var", "tt"}
# Zawsze pomijane — modyfikacja treści zepsułaby CSS/JS.
_ALWAYS_SKIP_TAGS = {"style", "script"}
# Elementy blokowe = granice parowania cudzysłowów (para nie przechodzi między
# akapitami). Elementy „inline" (em/i/b/span/a/strong…) są przezroczyste.
_BLOCK_TAGS = {
    "p", "div", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "aside", "header", "footer", "main", "nav",
    "td", "th", "dd", "dt", "figcaption", "caption", "body",
}  # fmt: skip


@dataclass(frozen=True)
class _QuoteChars:
    """Znaki cudzysłowów: podwójne i pojedyncze, otwierające i zamykające."""

    double_open: str
    double_close: str
    single_open: str
    single_close: str


# „…” / ‚…’ (pl), “…” / ‘…’ (en), „…“ / ‚…‘ (de)
_QUOTES_BY_LANG: dict[str, _QuoteChars] = {
    "pl": _QuoteChars("„", "”", "‚", "’"),
    "en": _QuoteChars("“", "”", "‘", "’"),
    "de": _QuoteChars("„", "“", "‚", "‘"),
}
_DEFAULT_QUOTES = _QUOTES_BY_LANG["en"]

# Znaki, po których cudzysłów jest OTWIERAJĄCY (poza białym znakiem/początkiem
# węzła). Wg roadmapy: ( « [ — plus warianty nawiasów i półpauza/pauza.
_OPEN_CONTEXT = frozenset("([{«‹—–―/")

# Wielokropek: trzy (lub więcej) kropki → jeden znak U+2026.
_ELLIPSIS_RE = re.compile(r"\.{3,}")
# Dialog: dywiz/półpauza na początku akapitu + spacja → pauza „— ".
_DIALOG_DASH_RE = re.compile(r"^[ \t]*[-–][ \t]+")
# Wtrącenie: „ - " / „ – " między słowami → „ — " (pauza, spacje zachowane).
_INTERWORD_DASH_RE = re.compile(r"(?<=\s)[-–](?=\s)")
# „Sieroty" (pl): samotny spójnik a/i/o/u/w/z + spacja → twarda spacja.
_NBSP_LETTERS_RE = re.compile(r"\b([aiouwzAIOUWZ]) ")
# Liczba + spacja + jednostka/litera (np. „10 km", „5 %").
_NBSP_NUM_UNIT_RE = re.compile(r"(?<=\d) (?=[^\W\d_]|[%°])")
# Liczba rzymska + spacja przed „w."/„r." (np. „XX w.", „XIX r.").
_NBSP_ROMAN_RE = re.compile(r"\b([IVXLCDM]+) (?=[wr]\.)")


@dataclass
class TypographyOptions:
    """Opcje fixera typografii.

    Każda reguła jest sterowana osobną flagą. Język ``language`` dobiera znaki
    cudzysłowów oraz włącza reguły językowe (twarda spacja po sierotach — pl).

    Attributes:
        language: ``pl`` / ``en`` / ``de`` — cudzysłowy i reguły językowe.
        fix_quotes: proste ``"`` i ``'`` → pary typograficzne wg języka.
        fix_dashes: pauza w dialogach i wtrąceniach (nie rusza łączników w słowach).
        fix_ellipsis: ``...`` → ``…``.
        nbsp_single_letters: pl — twarda spacja po samotnych a/i/o/u/w/z.
        nbsp_numbers_units: liczba + jednostka → twarda spacja (domyślnie OFF).
        skip_tags: tagi, których zawartość tekstowa nie jest ruszana.
    """

    language: str = "pl"
    fix_quotes: bool = True
    fix_dashes: bool = True
    fix_ellipsis: bool = True
    nbsp_single_letters: bool = True
    nbsp_numbers_units: bool = False
    skip_tags: set[str] = field(default_factory=lambda: set(_DEFAULT_SKIP_TAGS))


@dataclass
class TypographyReport:
    """Raport podmian: reguła → liczba, per plik i sumarycznie."""

    per_file: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(self, path: str, counts: dict[str, int]) -> None:
        """Zapisuje liczby podmian dla pliku (tylko gdy cokolwiek zmieniono)."""
        if any(counts.values()):
            self.per_file[path] = {rule: counts.get(rule, 0) for rule in _RULE_KEYS}

    def totals(self) -> dict[str, int]:
        """Sumaryczne liczby podmian per reguła (po wszystkich plikach)."""
        totals = dict.fromkeys(_RULE_KEYS, 0)
        for counts in self.per_file.values():
            for rule, value in counts.items():
                totals[rule] += value
        return totals

    @property
    def total_changes(self) -> int:
        """Łączna liczba wszystkich podmian."""
        return sum(sum(counts.values()) for counts in self.per_file.values())

    @property
    def changed_files(self) -> list[str]:
        """Posortowana lista plików ze zmianami."""
        return sorted(self.per_file)


class _QuoteState:
    """Stan parowania cudzysłowów: ostatni znaczący znak (dla open/close)."""

    __slots__ = ("prev_char",)

    def __init__(self) -> None:
        self.prev_char: str | None = None


def fix_typography(epub: Epub, options: TypographyOptions) -> TypographyReport:
    """Poprawia typografię dokumentów XHTML w otwartym EPUB-ie.

    Zmiany trafiają do bufora :class:`Epub` przez ``write_file`` (zapis na dysk
    należy do wywołującego przez ``epub.save()``). Plik jest zapisywany tylko, gdy
    reguły faktycznie coś podmieniły (idempotentność — drugi przebieg = 0 zmian).

    Args:
        epub: otwarty EPUB.
        options: włączone reguły i język.

    Returns:
        :class:`TypographyReport` — liczby podmian per reguła per plik i sumarycznie.
    """
    chars = _QUOTES_BY_LANG.get(options.language, _DEFAULT_QUOTES)
    report = TypographyReport()
    for item in _html_items(epub):
        internal_path = _manifest_path(epub, item)
        original = epub.read_file(internal_path)
        updated, counts = _fix_document(original, options, chars)
        if updated is not None and updated != original:
            epub.write_file(internal_path, updated)
        report.record(internal_path, counts)
    return report


def _fix_document(
    data: bytes, options: TypographyOptions, chars: _QuoteChars
) -> tuple[bytes | None, dict[str, int]]:
    """Parsuje dokument, stosuje reguły i (gdy były zmiany) serializuje z DOCTYPE."""
    counts = dict.fromkeys(_RULE_KEYS, 0)
    try:
        root, doctype = parse_untrusted_document(data)
    except (ValueError, etree.XMLSyntaxError):
        # „Brudny" lub pusty dokument — pomijamy bez wywracania całego EPUB-a.
        return None, counts
    _process_element(
        root, blocked=False, state=_QuoteState(), options=options, chars=chars, counts=counts
    )
    if not any(counts.values()):
        return None, counts
    return serialize_document(root, doctype), counts


def _process_element(
    element: etree._Element,
    *,
    blocked: bool,
    state: _QuoteState,
    options: TypographyOptions,
    chars: _QuoteChars,
    counts: dict[str, int],
) -> None:
    """Rekurencyjnie stosuje reguły do węzłów ``text``/``tail``.

    Bloki dostają świeży stan parowania cudzysłowów; elementy inline dzielą stan
    rodzica (para przechodzi przez ``<em>`` itd.).
    """
    tag = _local_name(element)
    blocked_here = blocked or tag in options.skip_tags or tag in _ALWAYS_SKIP_TAGS
    is_block = tag in _BLOCK_TAGS
    elem_state = _QuoteState() if is_block else state

    if element.text:
        element.text = _apply_rules(
            element.text,
            is_block_start=is_block,
            blocked=blocked_here,
            state=elem_state,
            options=options,
            chars=chars,
            counts=counts,
        )

    for child in element:
        if isinstance(child.tag, str):
            child_is_block = _local_name(child) in _BLOCK_TAGS
            if child_is_block:
                elem_state.prev_char = None  # granica bloku resetuje kontekst
            _process_element(
                child,
                blocked=blocked_here,
                state=elem_state,
                options=options,
                chars=chars,
                counts=counts,
            )
            if child_is_block:
                elem_state.prev_char = None
        if child.tail:
            child.tail = _apply_rules(
                child.tail,
                is_block_start=False,
                blocked=blocked_here,
                state=elem_state,
                options=options,
                chars=chars,
                counts=counts,
            )


def _apply_rules(
    text: str,
    *,
    is_block_start: bool,
    blocked: bool,
    state: _QuoteState,
    options: TypographyOptions,
    chars: _QuoteChars,
    counts: dict[str, int],
) -> str:
    """Stosuje włączone reguły do jednego węzła tekstowego."""
    if blocked:
        # Nie modyfikuj (code/pre/style…), ale przenieś stan parowania dalej —
        # cudzysłów tuż po </code> ma się poprawnie sparować.
        state.prev_char = text[-1]
        return text

    if options.fix_ellipsis:
        text = _sub_count(_ELLIPSIS_RE, "…", text, counts, RULE_ELLIPSIS)

    if options.fix_dashes:
        if is_block_start:
            text = _sub_count(_DIALOG_DASH_RE, "— ", text, counts, RULE_DASHES)
        text = _sub_count(_INTERWORD_DASH_RE, "—", text, counts, RULE_DASHES)

    if options.fix_quotes:
        text = _fix_quotes(text, state, chars, counts)

    if options.nbsp_single_letters and options.language == "pl":
        text = _sub_count(_NBSP_LETTERS_RE, "\\1" + NBSP, text, counts, RULE_NBSP_LETTERS)

    if options.nbsp_numbers_units:
        text = _sub_count(_NBSP_NUM_UNIT_RE, NBSP, text, counts, RULE_NBSP_NUMBERS)
        text = _sub_count(_NBSP_ROMAN_RE, "\\1" + NBSP, text, counts, RULE_NBSP_NUMBERS)

    if text:
        state.prev_char = text[-1]
    return text


def _fix_quotes(text: str, state: _QuoteState, chars: _QuoteChars, counts: dict[str, int]) -> str:
    """Zamienia proste ``"``/``'`` na pary typograficzne (heurystyka open/close).

    Stan (``prev_char``) wchodzi z poprzedniego węzła i jest aktualizowany znak po
    znaku — dzięki temu para poprawnie domyka się np. w ``child.tail`` za ``<em>``.
    """
    if '"' not in text and "'" not in text:
        return text
    result: list[str] = []
    prev = state.prev_char
    substitutions = 0
    for char in text:
        if char == '"':
            opening = prev is None or prev.isspace() or prev in _OPEN_CONTEXT
            replacement = chars.double_open if opening else chars.double_close
            result.append(replacement)
            prev = replacement
            substitutions += 1
        elif char == "'":
            opening = prev is None or prev.isspace() or prev in _OPEN_CONTEXT
            replacement = chars.single_open if opening else chars.single_close
            result.append(replacement)
            prev = replacement
            substitutions += 1
        else:
            result.append(char)
            prev = char
    counts[RULE_QUOTES] += substitutions
    return "".join(result)


def _sub_count(
    pattern: re.Pattern[str], repl: str, text: str, counts: dict[str, int], rule: str
) -> str:
    """Zamienia wg regexu i dolicza liczbę podmian do raportu reguły."""
    updated, n = pattern.subn(repl, text)
    counts[rule] += n
    return updated


def _html_items(epub: Epub) -> list[ManifestItem]:
    """Zwraca wpisy manifestu wskazujące dokumenty HTML/XHTML."""
    return [
        item
        for item in epub.manifest
        if item.media_type in _HTML_MEDIA_TYPES or _href_suffix(item.href) in {".html", ".xhtml"}
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


def _local_name(element: etree._Element) -> str:
    """Zwraca lokalną nazwę tagu bez przestrzeni nazw, małymi literami."""
    return etree.QName(element.tag).localname.lower()
