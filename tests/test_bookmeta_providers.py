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

import pytest

from epubforge.bookmeta import _http, fetch_by_isbn
from epubforge.bookmeta.providers import (
    BNProvider,
    GoogleBooksProvider,
    OpenLibraryProvider,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "bookmeta"

# ISBN-y użyte w testach (poprawne sumy kontrolne).
_ISBN_WIEDZMIN = "9788375780635"
_ISBN_FOX = "9780140328721"

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
    record = BNProvider().fetch_by_isbn(_ISBN_WIEDZMIN)
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
    assert BNProvider().fetch_by_isbn(_ISBN_FOX) is None


def test_bn_provider_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Błąd sieci (URL spoza mapy) → None, bez wyjątku."""
    _install_routes(monkeypatch, {})
    assert BNProvider().fetch_by_isbn(_ISBN_WIEDZMIN) is None


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
    record = BNProvider().fetch_by_isbn(_ISBN_WIEDZMIN)
    if record is None:
        pytest.skip("Brak dostępu do API BN (offline lub API niedostępne)")
    assert record.title
    assert record.source == "bn"
    assert record.page_count is not None
