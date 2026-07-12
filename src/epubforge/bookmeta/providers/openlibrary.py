"""Provider Open Library (``openlibrary.org``) — fallback dla wydań obcych.

Open Library zwraca rekord wydania spod ``/isbn/{isbn}.json``. Autorzy są tam
tylko referencjami (``/authors/OL…A``), więc ich nazwy dociągamy osobnymi
zapytaniami (z rozsądnym limitem). Wszystkie odczyty są defensywne.
"""

from __future__ import annotations

from typing import Any

from epubforge.bookmeta._http import DEFAULT_TIMEOUT, fetch_json
from epubforge.bookmeta._lang import to_iso639_1
from epubforge.bookmeta.model import BookRecord

_ISBN_URL = "https://openlibrary.org/isbn/{isbn}.json"
_AUTHOR_URL = "https://openlibrary.org{key}.json"
# Górny limit dociąganych autorów — chroni przed lawiną zapytań przy dziwnym rekordzie.
_MAX_AUTHORS = 8


class OpenLibraryProvider:
    """Źródło metadanych: Open Library (edycja po ISBN + nazwy autorów)."""

    name = "openlibrary"

    def fetch_by_isbn(
        self,
        isbn: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        title: str = "",
        author: str = "",
    ) -> BookRecord | None:
        """Pobiera i parsuje rekord wydania Open Library (``None`` przy braku/błędzie).

        ``title``/``author`` (podpowiedzi z EPUB) są ignorowane — OL wyszukuje tylko po ISBN.
        """
        data = fetch_json(_ISBN_URL.format(isbn=isbn), timeout=timeout)
        if not isinstance(data, dict):
            return None
        record = BookRecord(
            title=_title(data),
            creators=_authors(data.get("authors"), timeout),
            publisher=_first_str(data.get("publishers")),
            date=str(data.get("publish_date") or "").strip(),
            language=_language(data.get("languages")),
            isbn=isbn,
            page_count=_page_count(data.get("number_of_pages")),
            subjects=_str_list(data.get("subjects")),
            source="openlibrary",
        )
        return None if record.is_empty() else record


def _title(data: dict[str, Any]) -> str:
    """Składa tytuł z ``title`` + opcjonalnym ``subtitle``."""
    title = str(data.get("title") or "").strip()
    subtitle = str(data.get("subtitle") or "").strip()
    if title and subtitle:
        return f"{title}: {subtitle}"
    return title or subtitle


def _authors(authors: Any, timeout: float) -> list[str]:
    """Dociąga nazwy autorów z referencji ``/authors/OL…A`` (z limitem zapytań)."""
    if not isinstance(authors, list):
        return []
    names: list[str] = []
    for entry in authors[:_MAX_AUTHORS]:
        key = entry.get("key") if isinstance(entry, dict) else None
        if not isinstance(key, str) or not key.startswith("/"):
            continue
        detail = fetch_json(_AUTHOR_URL.format(key=key), timeout=timeout)
        if not isinstance(detail, dict):
            continue
        name = str(detail.get("name") or detail.get("personal_name") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _language(languages: Any) -> str:
    """Zwraca kod ISO 639-1 z pierwszej referencji ``/languages/xxx``."""
    if not isinstance(languages, list):
        return ""
    for entry in languages:
        key = entry.get("key") if isinstance(entry, dict) else None
        if isinstance(key, str) and "/" in key:
            mapped = to_iso639_1(key.rsplit("/", 1)[-1])
            if mapped:
                return mapped
    return ""


def _page_count(value: Any) -> int | None:
    """Zwraca liczbę stron jako ``int`` lub ``None`` (odporne na dziwne typy)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    return None


def _first_str(value: Any) -> str:
    """Zwraca pierwszy niepusty string z listy (np. ``publishers``) lub pusty."""
    if isinstance(value, list):
        for item in value:
            text = str(item or "").strip()
            if text:
                return text
    return ""


def _str_list(value: Any) -> list[str]:
    """Zwraca listę niepustych stringów (obsługuje ``subjects`` jako listę tekstów)."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result
