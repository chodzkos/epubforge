"""Testy providerów metadanych i łańcucha scalania (BN / Open Library / Google Books).

Wszystkie testy jednostkowe **mockują ``urllib.request.urlopen``** i czytają
zapisane fixtures (w tym prawdziwą odpowiedź BN) — zero ruchu sieciowego. Na końcu
jeden test za markerem ``integration`` odpytuje realne API BN (pomijany bez sieci).
"""

from __future__ import annotations

import urllib.error
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pytest

from epubforge.bookmeta import _http, chain, fetch_by_isbn
from epubforge.bookmeta.cache import MetadataCache, RateLimiter
from epubforge.bookmeta.providers import (
    BNProvider,
    GoogleBooksProvider,
    LubimyCzytacProvider,
    OpenLibraryProvider,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "bookmeta"

# ISBN-y użyte w testach (poprawne sumy kontrolne).
_ISBN_WIEDZMIN = "9788375780635"
_ISBN_FOX = "9780140328721"


def _bn() -> BNProvider:
    """BN z cache w RAM i zerowym limiterem — bez dysku i bez czekania w testach."""
    return BNProvider(cache=MetadataCache(), rate_limiter=RateLimiter(0.0))


@pytest.fixture(autouse=True)
def _fast_lubimyczytac(monkeypatch: pytest.MonkeyPatch) -> None:
    """Podmienia globalny provider LC w łańcuchu na szybki (cache w RAM, zero czekania).

    Domyślny łańcuch zawiera LubimyCzytac (scraping). Bez tego testy dotykałyby dysku
    (cache w katalogu configu) i realnie usypiały (rate limiter). Tu wstrzykujemy
    provider z cache ``:memory:`` i limiterem 0 s; nierozmapowany URL LC → ``URLError``
    → ``None`` (łańcuch po prostu idzie dalej).
    """
    lc = LubimyCzytacProvider(cache=MetadataCache(), rate_limiter=RateLimiter(0.0))
    monkeypatch.setattr(chain, "_LUBIMYCZYTAC", lc)
    monkeypatch.setattr(
        chain,
        "_DEFAULT_PROVIDERS",
        (_bn(), lc, OpenLibraryProvider(), GoogleBooksProvider()),
    )


# ── Atrapa sieci ────────────────────────────────────────────────────────────────


class _FakeResponse:
    """Atrapa odpowiedzi urlopen (context manager + ``read(n)``)."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self, amt: int | None = None) -> bytes:
        return self._data if amt is None or amt < 0 else self._data[:amt]

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _url_router(routes: dict[str, bytes]) -> Callable[..., _FakeResponse]:
    """Buduje atrapę urlopen mapującą pełny URL żądania na treść odpowiedzi.

    URL spoza mapy → ``URLError`` (jak realny brak trafienia), co pozwala testować
    zachowanie providera, gdy dane źródło nic nie zwraca.
    """

    def opener(request: Any, timeout: float | None = None) -> _FakeResponse:
        url = getattr(request, "full_url", request)
        if url not in routes:
            raise urllib.error.URLError(f"brak atrapy dla {url}")
        return _FakeResponse(routes[url])

    return opener


def _install_routes(monkeypatch: pytest.MonkeyPatch, routes: dict[str, bytes]) -> None:
    """Podmienia urlopen w kliencie HTTP na router URL→treść."""
    monkeypatch.setattr(_http.urllib.request, "urlopen", _url_router(routes))


def _fixture_bytes(name: str) -> bytes:
    """Wczytuje plik fixture jako bajty."""
    return (_FIXTURES / name).read_bytes()


# ── Provider BN ─────────────────────────────────────────────────────────────────


def _bn_url(isbn: str) -> str:
    return f"https://data.bn.org.pl/api/institutions/bibs.json?isbnIssn={isbn}&limit=1"


def test_bn_provider_parses_real_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prawdziwa odpowiedź BN → poprawny rekord (tytuł, autor, strony, deskryptory)."""
    _install_routes(monkeypatch, {_bn_url(_ISBN_WIEDZMIN): _fixture_bytes("bn_wiedzmin.json")})
    record = _bn().fetch_by_isbn(_ISBN_WIEDZMIN)
    assert record is not None
    assert record.title == "Ostatnie życzenie"
    assert record.creators == ["Sapkowski, Andrzej"]
    assert record.publisher == "SuperNOWA"
    assert record.date == "2014"
    assert record.language == "pl"
    assert record.page_count == 330
    assert record.series == "Wiedźmin"
    assert record.source == "bn"
    # Deskryptory przedmiotowe BN (pola 6XX z $2=DBN).
    assert "Fantasy" in record.subjects
    assert "Wiedźmin" in record.subjects


def test_bn_provider_empty_bibs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pusta lista ``bibs`` (książki nie ma w BN) → None."""
    _install_routes(monkeypatch, {_bn_url(_ISBN_FOX): b'{"bibs": []}'})
    assert _bn().fetch_by_isbn(_ISBN_FOX) is None


def test_bn_provider_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Błąd sieci (URL spoza mapy) → None, bez wyjątku."""
    _install_routes(monkeypatch, {})
    assert _bn().fetch_by_isbn(_ISBN_WIEDZMIN) is None


# ── Provider BN: fallback tytułowy (ISBN e-wydania nieobecny w katalogu) ──────────


def _bn_title_url(title: str) -> str:
    return f"https://data.bn.org.pl/api/institutions/bibs.json?title={quote_plus(title)}&limit=5"


def _install_recording_routes(
    monkeypatch: pytest.MonkeyPatch, routes: dict[str, bytes]
) -> list[str]:
    """Jak ``_install_routes``, ale zwraca listę URL-i żądań (do asercji „nie odpytano")."""
    calls: list[str] = []

    def opener(request: Any, timeout: float | None = None) -> _FakeResponse:
        url = getattr(request, "full_url", request)
        calls.append(url)
        if url not in routes:
            raise urllib.error.URLError(f"brak atrapy dla {url}")
        return _FakeResponse(routes[url])

    monkeypatch.setattr(_http.urllib.request, "urlopen", opener)
    return calls


# Minimalny rekord BN o INNYM tytule (do testu progu fuzzy).
_BN_MISMATCH = (
    b'{"bibs": [{"publicationYear": "1834", "marc": {"fields": ['
    b'{"245": {"subfields": [{"a": "Pan Tadeusz"}]}},'
    b'{"100": {"subfields": [{"a": "Mickiewicz, Adam"}]}}]}}]}'
)
_TITLE = "Ostatnie życzenie"
_AUTHOR = "Sapkowski, Andrzej"


def test_bn_fallback_by_title_when_isbn_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """ISBN e-booka nieobecny w BN + znany tytuł/autor → dopasowanie po tytule (fuzzy).

    ISBN rekordu pozostaje ISBN-em z pliku (NIE jest nadpisywany papierowym z BN).
    """
    routes = {
        _bn_url(_ISBN_FOX): b'{"bibs": []}',  # ISBN e-booka: pudło
        _bn_title_url(_TITLE): _fixture_bytes("bn_wiedzmin.json"),  # po tytule: trafienie
    }
    _install_routes(monkeypatch, routes)
    record = _bn().fetch_by_isbn(_ISBN_FOX, title=_TITLE, author=_AUTHOR)
    assert record is not None
    assert record.match_type == "fuzzy"
    assert record.title == "Ostatnie życzenie"
    assert record.creators == ["Sapkowski, Andrzej"]
    assert record.isbn == _ISBN_FOX  # ISBN pliku NIETKNIĘTY (nie papierowy z BN)


def test_bn_isbn_hit_skips_title_query(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trafienie po ISBN → match_type='isbn' i ZERO zapytań po tytule."""
    calls = _install_recording_routes(
        monkeypatch, {_bn_url(_ISBN_WIEDZMIN): _fixture_bytes("bn_wiedzmin.json")}
    )
    record = _bn().fetch_by_isbn(_ISBN_WIEDZMIN, title=_TITLE, author=_AUTHOR)
    assert record is not None
    assert record.match_type == "isbn"
    assert all("title=" not in url for url in calls)  # brak zapytania tytułowego


def test_bn_fuzzy_below_threshold_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """ISBN pudłuje + najlepsze dopasowanie poniżej progu → None (łańcuch idzie dalej)."""
    routes = {
        _bn_url(_ISBN_FOX): b'{"bibs": []}',
        _bn_title_url(_TITLE): _BN_MISMATCH,  # inny tytuł → niski score
    }
    _install_routes(monkeypatch, routes)
    assert _bn().fetch_by_isbn(_ISBN_FOX, title=_TITLE, author=_AUTHOR) is None


def test_bn_no_title_hint_skips_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """ISBN pudłuje + brak tytułu → brak drugiego (tytułowego) zapytania."""
    calls = _install_recording_routes(monkeypatch, {_bn_url(_ISBN_FOX): b'{"bibs": []}'})
    assert _bn().fetch_by_isbn(_ISBN_FOX) is None
    assert all("title=" not in url for url in calls)


def test_bn_cache_distinguishes_isbn_and_title(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cache rozróżnia zapytania isbn vs title — fallback nie nadpisuje wpisu ISBN."""
    provider = _bn()
    routes = {
        _bn_url(_ISBN_FOX): b'{"bibs": []}',
        _bn_title_url(_TITLE): _fixture_bytes("bn_wiedzmin.json"),
    }
    _install_routes(monkeypatch, routes)
    record = provider.fetch_by_isbn(_ISBN_FOX, title=_TITLE, author=_AUTHOR)
    assert record is not None and record.match_type == "fuzzy"

    cache = provider._ensure_cache()
    isbn_entry = cache.get("bn", _bn_url(_ISBN_FOX))
    title_entry = cache.get("bn", _bn_title_url(_TITLE))
    assert isbn_entry is not None and title_entry is not None  # dwa osobne wpisy
    assert isbn_entry != title_entry  # wpis ISBN NIE nadpisany odpowiedzią tytułową

    # Drugie wywołanie działa z cache (sieć odcięta) — wynik ten sam.
    _install_routes(monkeypatch, {})
    again = provider.fetch_by_isbn(_ISBN_FOX, title=_TITLE, author=_AUTHOR)
    assert again is not None and again.match_type == "fuzzy"


# ── Provider Open Library ────────────────────────────────────────────────────────


def test_openlibrary_provider_resolves_authors(monkeypatch: pytest.MonkeyPatch) -> None:
    """OL: edycja + dociągnięcie nazwy autora z osobnego zapytania."""
    routes = {
        f"https://openlibrary.org/isbn/{_ISBN_FOX}.json": _fixture_bytes(
            "openlibrary_edition.json"
        ),
        "https://openlibrary.org/authors/OL34184A.json": _fixture_bytes("openlibrary_author.json"),
    }
    _install_routes(monkeypatch, routes)
    record = OpenLibraryProvider().fetch_by_isbn(_ISBN_FOX)
    assert record is not None
    assert record.title == "Fantastic Mr Fox: A Roald Dahl classic"
    assert record.creators == ["Roald Dahl"]
    assert record.publisher == "Puffin"
    assert record.language == "en"
    assert record.page_count == 96
    assert record.source == "openlibrary"


def test_openlibrary_provider_missing_edition(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brak edycji w OL → None."""
    _install_routes(monkeypatch, {})
    assert OpenLibraryProvider().fetch_by_isbn(_ISBN_FOX) is None


# ── Provider Google Books ────────────────────────────────────────────────────────


def test_googlebooks_provider_parses_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    """GB: pierwszy wolumin → rekord z opisem i liczbą stron."""
    routes = {
        f"https://www.googleapis.com/books/v1/volumes?q=isbn:{_ISBN_FOX}": _fixture_bytes(
            "googlebooks_volumes.json"
        )
    }
    _install_routes(monkeypatch, routes)
    record = GoogleBooksProvider().fetch_by_isbn(_ISBN_FOX)
    assert record is not None
    assert record.title == "Fantastic Mr Fox"
    assert record.creators == ["Roald Dahl"]
    assert record.description.startswith("Someone's been stealing")
    assert record.page_count == 96
    assert record.language == "en"
    assert record.source == "googlebooks"


def test_googlebooks_provider_no_items(monkeypatch: pytest.MonkeyPatch) -> None:
    """Odpowiedź bez ``items`` → None."""
    routes = {
        f"https://www.googleapis.com/books/v1/volumes?q=isbn:{_ISBN_FOX}": b'{"totalItems": 0}'
    }
    _install_routes(monkeypatch, routes)
    assert GoogleBooksProvider().fetch_by_isbn(_ISBN_FOX) is None


# ── Łańcuch ─────────────────────────────────────────────────────────────────────


def test_chain_rejects_invalid_isbn_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zły ISBN → None i ZERO zapytań (urlopen nie może zostać wywołany)."""

    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("łańcuch nie powinien odpytywać sieci dla złego ISBN")

    monkeypatch.setattr(_http.urllib.request, "urlopen", explode)
    assert fetch_by_isbn("0000000000001") is None  # zła suma kontrolna ISBN-13


def test_chain_merges_bn_and_googlebooks(monkeypatch: pytest.MonkeyPatch) -> None:
    """BN daje podstawę, GB dopełnia brakujący opis (scalanie per pole)."""
    routes = {
        _bn_url(_ISBN_WIEDZMIN): _fixture_bytes("bn_wiedzmin.json"),
        f"https://openlibrary.org/isbn/{_ISBN_WIEDZMIN}.json": b'{"error": "notfound"}',
        f"https://www.googleapis.com/books/v1/volumes?q=isbn:{_ISBN_WIEDZMIN}": _fixture_bytes(
            "googlebooks_volumes.json"
        ),
    }
    _install_routes(monkeypatch, routes)
    record = fetch_by_isbn(_ISBN_WIEDZMIN)
    assert record is not None
    # Tytuł/wydawca/deskryptory pochodzą z BN (priorytet)…
    assert record.title == "Ostatnie życzenie"
    assert record.publisher == "SuperNOWA"
    assert "Fantasy" in record.subjects
    # …a opis (którego BN nie ma) dopełnia Google Books.
    assert record.description.startswith("Someone's been stealing")
    assert record.isbn == _ISBN_WIEDZMIN


def test_chain_falls_back_to_openlibrary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brak w BN → dane bierzemy z Open Library."""
    routes = {
        f"https://openlibrary.org/isbn/{_ISBN_FOX}.json": _fixture_bytes(
            "openlibrary_edition.json"
        ),
        "https://openlibrary.org/authors/OL34184A.json": _fixture_bytes("openlibrary_author.json"),
    }
    _install_routes(monkeypatch, routes)  # BN i GB spoza mapy → URLError → None
    record = fetch_by_isbn(_ISBN_FOX)
    assert record is not None
    assert record.creators == ["Roald Dahl"]
    assert record.source == "openlibrary"


def test_chain_returns_none_when_all_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Żadne źródło nie ma danych → None."""
    _install_routes(monkeypatch, {})
    assert fetch_by_isbn(_ISBN_FOX) is None


# ── Test integracyjny (realna sieć) ──────────────────────────────────────────────


@pytest.mark.integration
def test_bn_integration_real_network() -> None:
    """Realne zapytanie do API BN dla znanego ISBN (pomijane bez sieci)."""
    record = _bn().fetch_by_isbn(_ISBN_WIEDZMIN)
    if record is None:
        pytest.skip("Brak dostępu do API BN (offline lub API niedostępne)")
    assert record.title
    assert record.source == "bn"
    assert record.page_count is not None
