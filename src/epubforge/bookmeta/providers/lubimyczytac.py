"""Provider LubimyCzytac (``lubimyczytac.pl``) — opisy, cykle, kategorie, także bez ISBN.

Scraper napisany **od zera** (bez portowania kodu GPL) — korzystamy wyłącznie ze
struktury publicznych stron. Strategia parsowania: **JSON-LD first, HTML fallback
per pole**. Strona książki osadza ``application/ld+json`` typu ``schema.org/Book``,
ale bywa niepełny (brak opisu, wydawcy, czasem liczby stron) — te pola dobieramy
z HTML przez :mod:`html.parser` (stdlib). **Każde pole jest opcjonalne**: brak lub
zmiana layoutu → wartość ``None``/pusta, nigdy wyjątek.

Provider jest oznaczony jako „best effort": po redesignie serwisu może przestać
zwracać część pól. Ruch sieciowy jest grzecznościowy — przez cache i rate limiter
(:mod:`epubforge.bookmeta.cache`), jeden request na raz, z nagłówkiem identyfikującym
EpubForge.
"""

from __future__ import annotations

import json
import logging
import re
from html.parser import HTMLParser
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from urllib.parse import quote_plus

from epubforge.bookmeta._http import DEFAULT_TIMEOUT, fetch_bytes
from epubforge.bookmeta._lang import to_iso639_1
from epubforge.bookmeta.cache import DEFAULT_TTL_SECONDS, MetadataCache, RateLimiter
from epubforge.bookmeta.model import BookRecord, Candidate

logger = logging.getLogger(__name__)

_BASE = "https://lubimyczytac.pl"
_SEARCH_URL = _BASE + "/szukaj/ksiazki?phrase={phrase}"
# Minimalny odstęp między żądaniami do LC (grzecznościowy scraping).
_MIN_INTERVAL_SECONDS = 2.0
# Elementy void HTML — nie mają zamknięcia, więc nie liczą się do głębokości.
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)


def _user_agent() -> str:
    """Buduje User-Agent identyfikujący EpubForge (z wersją pakietu, jeśli dostępna)."""
    try:
        ver = version("epubforge")
    except PackageNotFoundError:  # pragma: no cover — pakiet zawsze zainstalowany w testach
        ver = "0.0"
    return f"EpubForge/{ver} (+https://github.com/chodzkos/epubforge)"


class LubimyCzytacProvider:
    """Źródło metadanych: LubimyCzytac (wyszukiwanie po ISBN oraz tytule/autorze)."""

    name = "lubimyczytac"

    def __init__(
        self,
        *,
        cache: MetadataCache | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        """Args:
        cache: cache odpowiedzi; ``None`` = leniwie utworzony w katalogu configu.
        rate_limiter: limiter żądań; ``None`` = domyślny (min. 2 s odstępu).
        """
        self._cache = cache
        self._rate_limiter = (
            rate_limiter if rate_limiter is not None else RateLimiter(_MIN_INTERVAL_SECONDS)
        )
        self._user_agent = _user_agent()

    # ── API providera ────────────────────────────────────────────────────────────

    def fetch_by_isbn(self, isbn: str, *, timeout: float = DEFAULT_TIMEOUT) -> BookRecord | None:
        """Pobiera pełny rekord dla ISBN (wyszukiwarka → pierwszy trafiony → strona)."""
        candidates = self.search_by_isbn(isbn, timeout=timeout)
        if not candidates:
            return None
        record = self.fetch_record(candidates[0].url, timeout=timeout)
        if record is not None and not record.isbn:
            record.isbn = isbn
        return record

    def search_by_isbn(self, isbn: str, *, timeout: float = DEFAULT_TIMEOUT) -> list[Candidate]:
        """Zwraca kandydatów z wyszukiwarki LC dla podanego ISBN."""
        return self._search(isbn, timeout=timeout)

    def search_title_author(
        self, title: str, author: str = "", *, timeout: float = DEFAULT_TIMEOUT
    ) -> list[Candidate]:
        """Zwraca kandydatów z wyszukiwarki LC dla „tytuł autor" (dla plików bez ISBN)."""
        query = f"{title} {author}".strip()
        return self._search(query, timeout=timeout) if query else []

    def fetch_record(self, url: str, *, timeout: float = DEFAULT_TIMEOUT) -> BookRecord | None:
        """Pobiera i parsuje stronę książki LC do :class:`BookRecord` (``None`` przy braku)."""
        if not url:
            return None
        html = self._get_html(url, timeout=timeout)
        if html is None:
            return None
        return _record_from_page(html)

    # ── Warstwa sieciowa (cache + rate limiter) ──────────────────────────────────

    def _search(self, phrase: str, *, timeout: float) -> list[Candidate]:
        """Wykonuje zapytanie do wyszukiwarki i parsuje kandydatów."""
        url = _SEARCH_URL.format(phrase=quote_plus(phrase))
        html = self._get_html(url, timeout=timeout)
        if html is None:
            return []
        return _candidates_from_search(html)

    def _get_html(self, url: str, *, timeout: float) -> str | None:
        """Zwraca HTML strony: z cache albo pobrany (z rate limitem) i zbuforowany."""
        cache = self._ensure_cache()
        cached = cache.get(self.name, url, ttl_seconds=DEFAULT_TTL_SECONDS)
        if cached is not None:
            return cached
        self._rate_limiter.wait()
        raw = fetch_bytes(url, timeout=timeout, user_agent=self._user_agent)
        if raw is None:
            return None
        html = raw.decode("utf-8", "replace")
        cache.set(self.name, url, html)
        return html

    def _ensure_cache(self) -> MetadataCache:
        """Leniwie tworzy domyślny cache w katalogu configu (bez side-effectów przy imporcie)."""
        if self._cache is None:
            from epubforge.core.config import config_dir

            self._cache = MetadataCache(config_dir() / "bookmeta_cache.sqlite")
        return self._cache


# ── Parsowanie strony książki ─────────────────────────────────────────────────────


class _BookPageParser(HTMLParser):
    """Zbiera z strony książki LC: bloki JSON-LD, opis, breadcrumb i pełny tekst.

    Pełny tekst służy do regexowego fallbacku pól, których nie ma w JSON-LD
    (wydawca, liczba stron). Głębokości elementów liczymy z pominięciem tagów void.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ldjson_blocks: list[str] = []
        self.description_parts: list[str] = []
        self.breadcrumbs: list[str] = []
        self.text_parts: list[str] = []
        self.publisher = ""
        self._ldjson_depth = 0
        self._desc_depth = 0
        self._crumb_depth = 0
        self._crumb_buf: list[str] = []
        self._pub_capture = False
        self._pub_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "script" and "ld+json" in a.get("type", ""):
            self._ldjson_depth = 1
        if a.get("id") == "book-description":
            self._desc_depth = 1
        elif self._desc_depth:
            self._desc_depth += self._depth_delta(tag)
        if a.get("itemprop") == "name" and self._crumb_depth == 0:
            self._crumb_depth = 1
            self._crumb_buf = []
        elif self._crumb_depth:
            self._crumb_depth += self._depth_delta(tag)
        # Wydawca: tekst pierwszego linku do /wydawnictwo/ (stabilniejsze niż regex).
        if tag == "a" and "/wydawnictwo/" in a.get("href", "") and not self.publisher:
            self._pub_capture = True
            self._pub_buf = []
        if tag == "br" and self._desc_depth:
            self.description_parts.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br" and self._desc_depth:
            self.description_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self._ldjson_depth:
            self._ldjson_depth = 0
        if self._desc_depth:
            self._desc_depth -= self._depth_delta(tag)
        if self._crumb_depth:
            self._crumb_depth -= self._depth_delta(tag)
            if self._crumb_depth == 0:
                text = "".join(self._crumb_buf).strip()
                if text:
                    self.breadcrumbs.append(text)
        if self._pub_capture and tag == "a":
            self._pub_capture = False
            self.publisher = " ".join("".join(self._pub_buf).split())

    def handle_data(self, data: str) -> None:
        if self._ldjson_depth:
            self.ldjson_blocks.append(data)
        else:
            self.text_parts.append(data)
        if self._desc_depth:
            self.description_parts.append(data)
        if self._crumb_depth:
            self._crumb_buf.append(data)
        if self._pub_capture:
            self._pub_buf.append(data)

    @staticmethod
    def _depth_delta(tag: str) -> int:
        """0 dla tagów void (bez zamknięcia), 1 dla pozostałych."""
        return 0 if tag in _VOID_TAGS else 1


def _record_from_page(html: str) -> BookRecord | None:
    """Buduje :class:`BookRecord` ze strony książki (JSON-LD first, HTML fallback)."""
    parser = _BookPageParser()
    parser.feed(html)
    book = _first_book_ldjson(parser.ldjson_blocks)
    text = " ".join(" ".join(parser.text_parts).split())

    title = _ld_str(book, "name")
    record = BookRecord(
        title=title,
        creators=_ld_authors(book),
        publisher=parser.publisher,
        date=_ld_str(book, "datePublished"),
        description=_clean_text(parser.description_parts),
        language=to_iso639_1(_ld_str(book, "inLanguage")),
        isbn=_ld_str(book, "isbn"),
        page_count=_ld_int(book, "numberOfPages") or _pages_from_text(text),
        subjects=_categories(parser.breadcrumbs, title),
        series=_ld_series(book),
        source="lubimyczytac",
    )
    return None if record.is_empty() else record


# ── Parsowanie wyników wyszukiwarki ────────────────────────────────────────────────


class _SearchParser(HTMLParser):
    """Zbiera kandydatów z listy wyników LC (karty ``book-card``)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.candidates: list[dict[str, Any]] = []
        self._author_active = False
        self._author_depth = 0
        self._author_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        classes = a.get("class", "").split()
        if tag == "a" and "book-card__title" in classes:
            self.candidates.append(
                {"title": a.get("title", "").strip(), "url": a.get("href", ""), "authors": []}
            )
        if self._author_active:
            if tag not in _VOID_TAGS:
                self._author_depth += 1
            return
        if tag == "div" and "book-card__author" in classes:
            self._author_active = True
            self._author_depth = 1
            self._author_buf = []

    def handle_endtag(self, tag: str) -> None:
        if not self._author_active:
            return
        self._author_depth -= 1
        if self._author_depth <= 0:
            self._author_active = False
            if self.candidates:
                self.candidates[-1]["authors"] = _split_authors("".join(self._author_buf))

    def handle_data(self, data: str) -> None:
        if self._author_active:
            self._author_buf.append(data)


def _candidates_from_search(html: str) -> list[Candidate]:
    """Parsuje kandydatów z HTML wyników wyszukiwarki (URL-e absolutne)."""
    parser = _SearchParser()
    parser.feed(html)
    result: list[Candidate] = []
    for card in parser.candidates:
        title = str(card.get("title", ""))
        url = str(card.get("url", ""))
        if not title or not url:
            continue
        if url.startswith("/"):
            url = _BASE + url
        result.append(
            Candidate(
                title=title, authors=list(card.get("authors", [])), url=url, source="lubimyczytac"
            )
        )
    return result


# ── Pomocniki JSON-LD i HTML ────────────────────────────────────────────────────────


def _first_book_ldjson(blocks: list[str]) -> dict[str, Any]:
    """Zwraca pierwszy blok JSON-LD typu ``Book`` (obsługuje też ``@graph``) lub pusty dict."""
    for block in blocks:
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        for node in _iter_ld_nodes(data):
            if isinstance(node, dict) and node.get("@type") == "Book":
                return node
    return {}


def _iter_ld_nodes(data: Any) -> list[Any]:
    """Rozwija JSON-LD do listy węzłów (dict, lista, ``@graph``)."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        graph = data.get("@graph")
        return graph if isinstance(graph, list) else [data]
    return []


def _ld_str(book: dict[str, Any], key: str) -> str:
    """Zwraca wartość pola JSON-LD jako przycięty string (lub pusty)."""
    value = book.get(key)
    return str(value).strip() if isinstance(value, (str, int, float)) else ""


def _ld_int(book: dict[str, Any], key: str) -> int | None:
    """Parsuje pole JSON-LD na dodatni ``int`` (np. ``numberOfPages``) lub ``None``."""
    value = book.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match:
            number = int(match.group(0))
            return number if number > 0 else None
    return None


def _ld_authors(book: dict[str, Any]) -> list[str]:
    """Zwraca nazwiska autorów z pola ``author`` (Person, lista Personów lub string)."""
    author = book.get("author")
    names: list[str] = []
    for entry in author if isinstance(author, list) else [author]:
        if isinstance(entry, dict):
            name = str(entry.get("name", "")).strip()
        elif isinstance(entry, str):
            name = entry.strip()
        else:
            name = ""
        if name and name not in names:
            names.append(name)
    return names


def _ld_series(book: dict[str, Any]) -> str:
    """Zwraca nazwę cyklu z ``isPartOfSeries`` (BookSeries) lub pusty łańcuch."""
    series = book.get("isPartOfSeries")
    if isinstance(series, list):
        series = series[0] if series else None
    if isinstance(series, dict):
        return str(series.get("name", "")).strip()
    return ""


def _categories(breadcrumbs: list[str], title: str) -> list[str]:
    """Wyciąga kategorie z okruszków (bez nazwy serwisu, „Książki" i tytułu książki)."""
    chrome = {"lubimyczytać", "lubimyczytac", "książki", "ksiazki", "strona główna"}
    title_norm = title.strip().lower()
    result: list[str] = []
    for crumb in breadcrumbs:
        low = crumb.strip().lower()
        if low in chrome or low == title_norm or not crumb.strip():
            continue
        if crumb not in result:
            result.append(crumb.strip())
    return result


def _clean_text(parts: list[str]) -> str:
    """Skleja fragmenty tekstu i normalizuje białe znaki (dla opisu)."""
    return " ".join("".join(parts).split())


def _split_authors(text: str) -> list[str]:
    """Rozbija tekst autorów (rozdzielony przecinkami) na listę nazwisk."""
    result: list[str] = []
    for part in text.replace("\xa0", " ").split(","):
        name = " ".join(part.split())
        if name and name not in result:
            result.append(name)
    return result


_PAGES_RE = re.compile(r"Liczba stron:\s*(\d+)")


def _pages_from_text(text: str) -> int | None:
    """Wyciąga liczbę stron z tekstu strony (pole ``Liczba stron:``) — fallback JSON-LD."""
    match = _PAGES_RE.search(text)
    return int(match.group(1)) if match else None
