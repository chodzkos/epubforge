"""Szukaj i zamień w plikach tekstowych EPUB — czysta logika (bez Qt).

Przeszukuje pliki edytowalne (XHTML/HTML/XML/OPF/NCX/SVG/CSS/TXT), dekodując je
jako UTF-8 z podmianą. :func:`replace_in_epub` zapisuje wynik **wyłącznie do
bufora** ``Epub.write_file`` — utrwalenie na dysk (``Epub.save``) należy do
wywołującego.

Pułapki (Etap 21):
- błędny regex → :class:`SearchPatternError` (czytelny komunikat, nie traceback);
- tryb ``regex=True`` używa pakietu ``regex`` z limitem czasu per plik
  (:data:`REGEX_TIMEOUT_SECONDS`); przekroczenie → :class:`SearchPatternError`
  (szukanie) albo wpis w ``report.skipped`` i przerwanie pętli (zamiana —
  wcześniejsze udane podmiany zostają w buforze);
- długość wzorca i wzorce dopasowujące pusty ciąg nadal odrzucamy
  (defense-in-depth, niezależnie od timeoutu);
- ``whole_words`` używa ``\b`` z ``re.UNICODE`` (poprawne dla polskich znaków);
- plik ze znakami zastępczymi ``�`` jest **wykluczony z REPLACE** (ryzyko
  utrwalenia uszkodzenia) — trafia do ``report.skipped``; szukanie jest dozwolone.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import regex as regex_lib

from epubforge.core.epub import Epub
from epubforge.core.textutil import decode_text, offset_to_line_col, resolve_internal_path

CancelCheck = Callable[[], bool]

# Maksymalna długość wzorca — proste zabezpieczenie przed katastroficznym regexem.
MAX_PATTERN_LENGTH = 1000
# Twardy limit czasu jednego wywołania matchera (finditer/subn) per plik.
REGEX_TIMEOUT_SECONDS = 1.0
REGEX_TIMEOUT_MESSAGE = "Wyrażenie regularne przekroczyło limit czasu. Uprość wzorzec."
# Maksymalna długość podglądu linii z trafieniem.
_PREVIEW_LIMIT = 160

_TEXT_SUFFIXES = frozenset(
    {".xhtml", ".html", ".htm", ".xml", ".opf", ".ncx", ".txt", ".svg", ".css"}
)
_TEXT_MEDIA_TYPES = frozenset(
    {
        "application/xhtml+xml",
        "text/html",
        "application/xml",
        "text/xml",
        "application/oebps-package+xml",
        "application/x-dtbncx+xml",
        "image/svg+xml",
        "text/css",
    }
)


class SearchError(ValueError):
    """Ogólny błąd wyszukiwania/zamiany."""


class SearchPatternError(SearchError):
    """Błędny wzorzec (regex, zbyt długi lub dopasowujący pusty ciąg)."""


@dataclass(frozen=True)
class SearchHit:
    """Pojedyncze trafienie wyszukiwania."""

    internal_path: str
    line: int  # 1-based
    column: int  # 1-based
    preview: str  # linia z trafieniem, przycięta


@dataclass(frozen=True)
class ReplaceResult:
    """Liczba podmian w jednym pliku."""

    internal_path: str
    count: int


@dataclass
class ReplaceReport:
    """Raport zamiany: podmiany per plik oraz pliki pominięte z powodem."""

    replaced: list[ReplaceResult] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Łączna liczba podmian we wszystkich plikach."""
        return sum(result.count for result in self.replaced)

    @property
    def changed_files(self) -> list[str]:
        """Ścieżki plików, w których dokonano podmian."""
        return [result.internal_path for result in self.replaced]


def search_epub(
    epub: Epub,
    query: str,
    *,
    regex: bool = False,
    case_sensitive: bool = False,
    whole_words: bool = False,
    paths: Iterable[str] | None = None,
    should_cancel: CancelCheck | None = None,
) -> list[SearchHit]:
    """Wyszukuje ``query`` w plikach tekstowych EPUB-a.

    Args:
        epub: otwarty EPUB.
        query: fraza (literalna albo regex, zależnie od ``regex``).
        regex: traktuj ``query`` jako wyrażenie regularne.
        case_sensitive: rozróżniaj wielkość liter.
        whole_words: dopasuj tylko całe słowa (``\\b`` z ``re.UNICODE``).
        paths: ogranicz do tych ścieżek wewnętrznych (``None`` = wszystkie tekstowe).
        should_cancel: predykat przerwania (dla dużych książek w wątku roboczym).

    Returns:
        Lista :class:`SearchHit` w kolejności plików i wystąpień.

    Raises:
        SearchPatternError: gdy wzorzec jest błędny, zbyt długi, pusty
            albo przekroczył :data:`REGEX_TIMEOUT_SECONDS` na którymś pliku.
    """
    if not query:
        return []
    pattern, timed = _compile(
        query, regex=regex, case_sensitive=case_sensitive, whole_words=whole_words
    )
    hits: list[SearchHit] = []
    for internal in _searchable_paths(epub, paths):
        if should_cancel is not None and should_cancel():
            break
        text, _replaced = decode_text(epub.read_file(internal))
        try:
            for match in _finditer(pattern, text, timed=timed):
                if match.start() == match.end():  # pomijamy dopasowania zerowej długości
                    continue
                line, column = offset_to_line_col(text, match.start())
                hits.append(SearchHit(internal, line, column, _preview(text, match.start())))
        except TimeoutError as exc:
            raise SearchPatternError(REGEX_TIMEOUT_MESSAGE) from exc
    return hits


def replace_in_epub(
    epub: Epub,
    query: str,
    replacement: str,
    *,
    regex: bool = False,
    case_sensitive: bool = False,
    whole_words: bool = False,
    paths: Iterable[str] | None = None,
    should_cancel: CancelCheck | None = None,
) -> ReplaceReport:
    """Zamienia ``query`` na ``replacement`` w plikach tekstowych, pisząc do BUFORA.

    Zapisuje przez :meth:`Epub.write_file` (bufor w pamięci) — utrwalenie na dysk
    robi użytkownik przez :meth:`Epub.save`. Pliki ze znakami zastępczymi ``�``
    są pomijane (trafiają do ``report.skipped``).

    Raises:
        SearchPatternError: gdy wzorzec jest błędny lub podstawienie ma złą referencję.

    Timeout matchera na jednym pliku nie wycofuje wcześniejszych podmian
    (ten sam kontrakt co przy ``should_cancel``): plik ląduje w ``skipped``,
    dalsze pliki nie są ruszane, raport wraca z tym, co już zapisano do bufora.
    """
    report = ReplaceReport()
    if not query:
        return report
    pattern, timed = _compile(
        query, regex=regex, case_sensitive=case_sensitive, whole_words=whole_words
    )
    # W trybie literalnym podstawienie MUSI być dosłowne (bez interpretacji \1, \g<>).
    repl: str | Callable[[re.Match[str]], str] = replacement if regex else (lambda _m: replacement)

    for internal in _searchable_paths(epub, paths):
        if should_cancel is not None and should_cancel():
            break
        text, replaced_chars = decode_text(epub.read_file(internal))
        if replaced_chars:
            report.skipped.append((internal, "plik zawiera znaki nie-UTF-8 (�)"))
            continue
        try:
            new_text, count = _subn(pattern, repl, text, timed=timed)
        except TimeoutError:
            report.skipped.append((internal, REGEX_TIMEOUT_MESSAGE))
            break
        except (re.error, regex_lib.error) as exc:
            raise SearchPatternError(f"Niepoprawne podstawienie: {exc}") from exc
        if count and new_text != text:
            epub.write_file(internal, new_text.encode("utf-8"))
            report.replaced.append(ReplaceResult(internal, count))
    return report


def _compile(
    query: str,
    *,
    regex: bool,
    case_sensitive: bool,
    whole_words: bool,
) -> tuple[Any, bool]:
    """Kompiluje wzorzec z opcjami; błędy mapuje na :class:`SearchPatternError`.

    Returns:
        Para ``(wzorzec, timed)`` — ``timed=True`` oznacza silnik ``regex``
        z timeoutem na wykonaniu (nie na ``compile``).
    """
    if len(query) > MAX_PATTERN_LENGTH:
        raise SearchPatternError(f"Wzorzec jest zbyt długi (max {MAX_PATTERN_LENGTH} znaków).")
    core = query if regex else re.escape(query)
    if whole_words:
        core = rf"\b(?:{core})\b"
    if regex:
        flags = regex_lib.UNICODE | (0 if case_sensitive else regex_lib.IGNORECASE)
        try:
            compiled: Any = regex_lib.compile(core, flags)
        except regex_lib.error as exc:
            raise SearchPatternError(f"Niepoprawny wzorzec: {exc}") from exc
    else:
        flags = re.UNICODE | (0 if case_sensitive else re.IGNORECASE)
        try:
            compiled = re.compile(core, flags)
        except re.error as exc:
            raise SearchPatternError(f"Niepoprawny wzorzec: {exc}") from exc
    if compiled.search("") is not None:
        raise SearchPatternError("Wzorzec dopasowuje pusty ciąg — doprecyzuj go.")
    return compiled, regex


def _finditer(pattern: Any, text: str, *, timed: bool) -> Any:
    """``finditer`` z timeoutem dla silnika ``regex``."""
    if timed:
        return pattern.finditer(text, timeout=REGEX_TIMEOUT_SECONDS)
    return pattern.finditer(text)


def _subn(pattern: Any, repl: Any, text: str, *, timed: bool) -> tuple[str, int]:
    """``subn`` z timeoutem dla silnika ``regex``."""
    if timed:
        result: tuple[str, int] = pattern.subn(repl, text, timeout=REGEX_TIMEOUT_SECONDS)
        return result
    result = pattern.subn(repl, text)
    return result


def _searchable_paths(epub: Epub, paths: Iterable[str] | None) -> list[str]:
    """Zwraca posortowaną listę ścieżek tekstowych (opcjonalnie ograniczoną do ``paths``)."""
    media_types = _media_type_map(epub)
    if paths is not None:
        wanted = list(dict.fromkeys(paths))  # dedup, zachowaj kolejność
        return [p for p in wanted if _is_searchable(p, media_types.get(p))]
    skip = {"mimetype", "META-INF/container.xml"}
    return sorted(
        name
        for name in epub.list_files()
        if name not in skip and _is_searchable(name, media_types.get(name))
    )


def _media_type_map(epub: Epub) -> dict[str, str]:
    """Buduje mapę ``ścieżka wewnętrzna → media-type`` z manifestu OPF."""
    opf_dir = epub.opf_dir()
    return {resolve_internal_path(item.href, opf_dir): item.media_type for item in epub.manifest}


def _is_searchable(internal_path: str, media_type: str | None) -> bool:
    """Czy plik jest tekstem do przeszukania (po media-type lub rozszerzeniu)."""
    if media_type and media_type.lower() in _TEXT_MEDIA_TYPES:
        return True
    return posixpath.splitext(internal_path)[1].lower() in _TEXT_SUFFIXES


def _preview(text: str, offset: int) -> str:
    """Zwraca przyciętą linię zawierającą trafienie (do podglądu w drzewie wyników)."""
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    line = text[start:] if end == -1 else text[start:end]
    stripped = line.strip()
    if len(stripped) > _PREVIEW_LIMIT:
        return stripped[:_PREVIEW_LIMIT] + "…"
    return stripped
