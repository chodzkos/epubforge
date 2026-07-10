"""Testy warstwy metadanych: walidacja ISBN, klient HTTP, model scalania.

Testy klienta HTTP mockują ``urllib.request.urlopen`` — nie wychodzą do sieci.
Wzorzec ``_FakeResponse`` odwzorowuje kontrakt odpowiedzi (context manager +
``read(n)``), więc sprawdzamy też limit rozmiaru i odrzucanie nie-https URL.
"""

from __future__ import annotations

import urllib.error
from collections.abc import Callable
from typing import Any

import pytest

from epubforge.bookmeta import _http, extract_isbn_from_epub, validate_isbn
from epubforge.bookmeta._lang import to_iso639_1
from epubforge.bookmeta.isbn import _find_isbn_in_text
from epubforge.bookmeta.model import BookRecord
from epubforge.core import ManifestItem

# ── Walidacja ISBN ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("978-83-7578-063-5", "9788375780635"),  # ISBN-13 z myślnikami
        ("9788375780635", "9788375780635"),
        ("0-306-40615-2", "0306406152"),  # ISBN-10
        ("0306406152", "0306406152"),
        ("080442957X", "080442957X"),  # ISBN-10 z kontrolnym X
        ("ISBN 978-0-306-40615-7", "9780306406157"),  # prefiks + separatory
    ],
)
def test_validate_isbn_accepts_valid(text: str, expected: str) -> None:
    """Poprawne ISBN-y (10/13, separatory, prefiks, X) → znormalizowana postać."""
    assert validate_isbn(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "1234567890",  # zła suma kontrolna ISBN-10
        "9788375780634",  # zła suma kontrolna ISBN-13
        "97883757806350",  # za długi
        "978837578063",  # za krótki
        "X788375780635",  # X w złym miejscu
        "abcdefghij",
    ],
)
def test_validate_isbn_rejects_invalid(text: str) -> None:
    """Błędny ISBN (suma kontrolna, długość, śmieci) → None (zero zapytań)."""
    assert validate_isbn(text) is None


# ── Klient HTTP ─────────────────────────────────────────────────────────────────


class _FakeResponse:
    """Minimalna atrapa odpowiedzi urlopen (context manager + ``read(n)``)."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self, amt: int | None = None) -> bytes:
        return self._data if amt is None or amt < 0 else self._data[:amt]

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _opener(body: bytes | Exception) -> Callable[..., _FakeResponse]:
    """Buduje atrapę urlopen zwracającą ``body`` (albo rzucającą wyjątek)."""

    def opener(request: Any, timeout: float | None = None) -> _FakeResponse:
        if isinstance(body, Exception):
            raise body
        return _FakeResponse(body)

    return opener


def test_fetch_json_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Poprawny JSON spod https jest dekodowany."""
    monkeypatch.setattr(_http.urllib.request, "urlopen", _opener(b'{"ok": true}'))
    assert _http.fetch_json("https://example.org/x.json") == {"ok": True}


def test_fetch_bytes_rejects_non_https(monkeypatch: pytest.MonkeyPatch) -> None:
    """URL o schemacie innym niż https jest odrzucany BEZ wywołania urlopen."""

    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("urlopen nie powinno zostać wywołane dla http://")

    monkeypatch.setattr(_http.urllib.request, "urlopen", explode)
    assert _http.fetch_bytes("http://example.org/x.json") is None


def test_fetch_json_over_limit_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Odpowiedź większa niż MAX_BYTES jest ucinana → zepsuty JSON → None."""
    oversized = b'{"x": "' + b"a" * (_http.MAX_BYTES + 100) + b'"}'
    monkeypatch.setattr(_http.urllib.request, "urlopen", _opener(oversized))
    assert _http.fetch_json("https://example.org/big.json") is None


def test_fetch_bytes_truncates_to_max(monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch_bytes nigdy nie zwraca więcej niż MAX_BYTES bajtów."""
    monkeypatch.setattr(_http.urllib.request, "urlopen", _opener(b"z" * (_http.MAX_BYTES * 2)))
    data = _http.fetch_bytes("https://example.org/big")
    assert data is not None
    assert len(data) == _http.MAX_BYTES


def test_fetch_json_timeout_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Timeout/błąd sieci → None (żaden wyjątek nie wychodzi na zewnątrz)."""
    monkeypatch.setattr(
        _http.urllib.request, "urlopen", _opener(urllib.error.URLError("timed out"))
    )
    assert _http.fetch_json("https://example.org/x.json") is None


def test_fetch_json_invalid_json_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Niepoprawny JSON → None."""
    monkeypatch.setattr(_http.urllib.request, "urlopen", _opener(b"<html>not json</html>"))
    assert _http.fetch_json("https://example.org/x.json") is None


# ── Mapowanie języków ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("code", "expected"),
    [("pol", "pl"), ("eng", "en"), ("ger", "de"), ("deu", "de"), ("pl", "pl"), ("EN", "en")],
)
def test_language_mapping(code: str, expected: str) -> None:
    """Kody 3-literowe i 2-literowe mapują się na ISO 639-1."""
    assert to_iso639_1(code) == expected


def test_language_mapping_unknown() -> None:
    """Nieznany kod → pusty łańcuch."""
    assert to_iso639_1("xyz") == ""
    assert to_iso639_1("") == ""


# ── Scalanie rekordów ───────────────────────────────────────────────────────────


def test_filled_from_fills_only_empty_fields() -> None:
    """filled_from dopełnia puste pola, nie nadpisując istniejących."""
    base = BookRecord(title="Tytuł", creators=["A"], source="bn")
    extra = BookRecord(
        title="Inny",
        creators=["B"],
        publisher="Wydawca",
        description="Opis",
        page_count=200,
        subjects=["temat"],
        source="googlebooks",
    )
    merged = base.filled_from(extra)
    assert merged.title == "Tytuł"  # istniejące ma priorytet
    assert merged.creators == ["A"]  # istniejąca lista nie jest mieszana
    assert merged.publisher == "Wydawca"  # puste dopełnione
    assert merged.description == "Opis"
    assert merged.page_count == 200
    assert merged.subjects == ["temat"]
    assert merged.source == "bn"  # źródło bazowe zachowane


def test_filled_from_does_not_mutate_arguments() -> None:
    """filled_from zwraca nowy rekord, nie modyfikując bazy ani extra."""
    base = BookRecord(title="T")
    extra = BookRecord(publisher="W", subjects=["x"])
    base.filled_from(extra)
    assert base.publisher == ""
    assert extra.subjects == ["x"]


def test_is_empty() -> None:
    """is_empty rozpoznaje rekord bez użytecznych danych."""
    assert BookRecord().is_empty()
    assert BookRecord(source="bn").is_empty()  # samo źródło to nie dane
    assert not BookRecord(title="X").is_empty()
    assert not BookRecord(page_count=1).is_empty()


# ── Ekstrakcja ISBN z EPUB ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ISBN 978-83-8069-285-5", "9788380692855"),
        ("na stronie redakcyjnej: ISBN: 0-306-40615-2 druk", "0306406152"),
        ("numer 9788380692855 w treści", "9788380692855"),
        ("brak numeru książki", None),
        ("ISBN 978-83-8069-285-0 (zła suma)", None),  # zła suma kontrolna → odrzucony
    ],
)
def test_find_isbn_in_text(text: str, expected: str | None) -> None:
    """_find_isbn_in_text zwraca pierwszy poprawny ISBN (suma kontrolna) lub None."""
    assert _find_isbn_in_text(text) == expected


class _FakeEpub:
    """Atrapa Epub: manifest/spine/opf_dir/read_file dla extract_isbn_from_epub."""

    def __init__(self, docs: dict[str, bytes]) -> None:
        self._docs = docs
        self.manifest = [
            ManifestItem(id="d1", href="text/redakcyjna.xhtml", media_type="application/xhtml+xml"),
            ManifestItem(id="d2", href="text/rozdzial.xhtml", media_type="application/xhtml+xml"),
        ]
        self.spine = ["d1", "d2"]

    def opf_dir(self) -> str:
        return "OEBPS"

    def read_file(self, path: str) -> bytes:
        return self._docs[path]


def test_extract_isbn_from_epub_finds_in_front_matter() -> None:
    """ISBN ze strony redakcyjnej (pierwszy dokument spine) jest znajdowany."""
    epub = _FakeEpub(
        {
            "OEBPS/text/redakcyjna.xhtml": b"<html>ISBN 978-83-8069-285-5</html>",
            "OEBPS/text/rozdzial.xhtml": b"<html>tresc</html>",
        }
    )
    assert extract_isbn_from_epub(epub) == "9788380692855"  # type: ignore[arg-type]


def test_extract_isbn_from_epub_missing_returns_none() -> None:
    """Brak ISBN w przejrzanych dokumentach → None (odczyt defensywny)."""
    epub = _FakeEpub({"OEBPS/text/redakcyjna.xhtml": b"<html>bez numeru</html>"})
    # d2 celowo nieobecny w docs → KeyError pominięty, nie przerywa
    assert extract_isbn_from_epub(epub) is None  # type: ignore[arg-type]
