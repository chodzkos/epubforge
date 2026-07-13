"""Provider Google Books (``googleapis.com/books``) — fallback z opisami.

Google Books bywa ostatnim ogniwem łańcucha: jego mocną stroną są **opisy**
marketingowe (których BN nie ma) oraz ``pageCount``. Odpowiedź to lista ``items``;
bierzemy pierwszy trafiony wolumin. Kod języka jest już dwuliterowy (ISO 639-1).
"""

from __future__ import annotations

from typing import Any

from epubforge.bookmeta._http import DEFAULT_TIMEOUT, fetch_json
from epubforge.bookmeta._lang import to_iso639_1
from epubforge.bookmeta.model import BookRecord

_API_URL = "https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
# Pin hosta API (obrona przed SSRF, gdyby URL kiedyś składano z danych zewnętrznych).
_HOSTS = frozenset({"www.googleapis.com"})


class GoogleBooksProvider:
    """Źródło metadanych: Google Books (wyszukiwanie po ISBN)."""

    name = "googlebooks"

    def fetch_by_isbn(
        self,
        isbn: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        title: str = "",
        author: str = "",
    ) -> BookRecord | None:
        """Pobiera i parsuje pierwszy wolumin Google Books (``None`` przy braku/błędzie).

        ``title``/``author`` (podpowiedzi z EPUB) są ignorowane — GB wyszukuje tylko po ISBN.
        """
        data = fetch_json(_API_URL.format(isbn=isbn), timeout=timeout, allowed_hosts=_HOSTS)
        info = _volume_info(data)
        if info is None:
            return None
        record = BookRecord(
            title=_title(info),
            creators=_str_list(info.get("authors")),
            publisher=str(info.get("publisher") or "").strip(),
            date=str(info.get("publishedDate") or "").strip(),
            description=str(info.get("description") or "").strip(),
            language=to_iso639_1(str(info.get("language") or "")),
            isbn=isbn,
            page_count=_page_count(info.get("pageCount")),
            subjects=_str_list(info.get("categories")),
            source="googlebooks",
        )
        return None if record.is_empty() else record


def _volume_info(data: Any) -> dict[str, Any] | None:
    """Wyłuskuje ``volumeInfo`` z pierwszego elementu ``items`` odpowiedzi."""
    if not isinstance(data, dict):
        return None
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    info = first.get("volumeInfo") if isinstance(first, dict) else None
    return info if isinstance(info, dict) else None


def _title(info: dict[str, Any]) -> str:
    """Składa tytuł z ``title`` + opcjonalnym ``subtitle``."""
    title = str(info.get("title") or "").strip()
    subtitle = str(info.get("subtitle") or "").strip()
    if title and subtitle:
        return f"{title}: {subtitle}"
    return title or subtitle


def _page_count(value: Any) -> int | None:
    """Zwraca liczbę stron jako dodatni ``int`` lub ``None``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    return None


def _str_list(value: Any) -> list[str]:
    """Zwraca listę niepustych, unikalnych stringów z pola listowego."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result
