"""Testy providera LubimyCzytac (:mod:`epubforge.bookmeta.providers.lubimyczytac`).

Parsowanie działa na **zapisanych, realnych fixtures HTML** (``tests/fixtures/lc/``);
ścieżka sieciowa jest mockowana (``urllib.request.urlopen``). Sprawdzamy też, że
trafienie w cache nie generuje żadnego żądania HTTP.
"""

from __future__ import annotations

import urllib.error
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from epubforge.bookmeta import _http
from epubforge.bookmeta.cache import MetadataCache, RateLimiter
from epubforge.bookmeta.providers.lubimyczytac import (
    LubimyCzytacProvider,
    _candidates_from_search,
    _record_from_page,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "lc"
_WITCHER_URL = "https://lubimyczytac.pl/ksiazka/303348/wiedzmin-ostatnie-zyczenie"


def _fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


# ── Parsowanie strony książki (bez sieci) ────────────────────────────────────────


def test_parse_rich_book_page() -> None:
    """Bogata strona (JSON-LD + HTML) → komplet pól (opis, strony, cykl, kategorie)."""
    record = _record_from_page(_fixture("book_witcher.html"))
    assert record is not None
    assert record.title == "Wiedźmin. Ostatnie życzenie"
    assert record.creators == ["Andrzej Sapkowski"]
    assert record.publisher == "Ringier Axel Springer Polska"
    assert record.date == "2016-04-20"
    assert record.language == "pl"
    assert record.isbn == "9788380692855"
    assert record.page_count == 48
    assert record.series == "Wiedźmin"
    assert record.subjects == ["Komiksy"]
    assert record.description.startswith("Wiedźmina przedstawiać nie trzeba")
    assert record.source == "lubimyczytac"


def test_parse_sparse_book_page() -> None:
    """Uboga JSON-LD (bez stron/serii) → rekord nadal poprawny, brakujące pola puste."""
    record = _record_from_page(_fixture("book_raid.html"))
    assert record is not None
    assert record.title == "Managing RAID on Linux"
    assert record.publisher == "O'Reilly Media"
    assert record.page_count is None  # brak w JSON-LD i w HTML
    assert record.series == ""
    assert record.subjects  # kategorie z breadcrumb obecne


def test_parse_broken_layout_returns_none() -> None:
    """Zepsuty/niezwiązany layout → None, nigdy wyjątek."""
    assert _record_from_page("<html><body>nic tu nie ma</body></html>") is None
    assert _record_from_page("") is None


def test_search_candidates_parse() -> None:
    """Wyniki wyszukiwarki → kandydaci z tytułem, autorami i absolutnym URL-em."""
    candidates = _candidates_from_search(_fixture("search_witcher.html"))
    assert len(candidates) == 2
    first = candidates[0]
    assert first.title == "Wiedźmin. Ostatnie życzenie"
    assert "Andrzej Sapkowski" in first.authors
    assert first.url.startswith("https://lubimyczytac.pl/ksiazka/")
    assert first.source == "lubimyczytac"


# ── Ścieżka sieciowa (mock urlopen) ──────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self, amt: int | None = None) -> bytes:
        return self._data if amt is None or amt < 0 else self._data[:amt]

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _router(routes: dict[str, bytes], counter: list[int]) -> Callable[..., _FakeResponse]:
    def opener(request: Any, timeout: float | None = None) -> _FakeResponse:
        counter[0] += 1
        url = getattr(request, "full_url", request)
        if url not in routes:
            raise urllib.error.URLError(f"brak atrapy dla {url}")
        return _FakeResponse(routes[url])

    return opener


def _provider(cache: MetadataCache | None = None) -> LubimyCzytacProvider:
    """Provider z wstrzykniętym cache i rate limiterem bez realnego czekania."""
    return LubimyCzytacProvider(
        cache=cache if cache is not None else MetadataCache(),
        rate_limiter=RateLimiter(0.0),
    )


def test_fetch_by_isbn_via_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch_by_isbn: wyszukiwarka → pierwszy kandydat → pełny rekord."""
    isbn = "9788380692855"
    search_url = f"https://lubimyczytac.pl/szukaj/ksiazki?phrase={isbn}"
    routes = {
        search_url: _fixture("search_witcher.html").encode("utf-8"),
        _WITCHER_URL: _fixture("book_witcher.html").encode("utf-8"),
    }
    calls = [0]
    monkeypatch.setattr(_http.urllib.request, "urlopen", _router(routes, calls))
    record = _provider().fetch_by_isbn(isbn)
    assert record is not None
    assert record.title == "Wiedźmin. Ostatnie życzenie"
    assert record.isbn == isbn
    assert calls[0] == 2  # jeden request na wyszukiwarkę, jeden na stronę


def test_cache_hit_skips_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strona w cache → 0 wywołań urlopen."""
    cache = MetadataCache()
    cache.set("lubimyczytac", _WITCHER_URL, _fixture("book_witcher.html"))

    def explode(*_a: object, **_k: object) -> None:
        raise AssertionError("urlopen nie powinno zostać wywołane przy trafieniu w cache")

    monkeypatch.setattr(_http.urllib.request, "urlopen", explode)
    record = _provider(cache).fetch_record(_WITCHER_URL)
    assert record is not None
    assert record.title == "Wiedźmin. Ostatnie życzenie"


def test_fetch_stores_in_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pierwszy fetch zapisuje do cache; drugi nie dotyka sieci."""
    cache = MetadataCache()
    routes = {_WITCHER_URL: _fixture("book_witcher.html").encode("utf-8")}
    calls = [0]
    monkeypatch.setattr(_http.urllib.request, "urlopen", _router(routes, calls))
    provider = _provider(cache)
    assert provider.fetch_record(_WITCHER_URL) is not None
    assert provider.fetch_record(_WITCHER_URL) is not None
    assert calls[0] == 1  # drugie wywołanie z cache


def test_fetch_record_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Błąd sieci → None, bez wyjątku."""
    calls = [0]
    monkeypatch.setattr(_http.urllib.request, "urlopen", _router({}, calls))
    assert _provider().fetch_record(_WITCHER_URL) is None
