"""Łańcuch providerów — scala metadane z wielu źródeł w jeden :class:`BookRecord`.

Kolejność ma znaczenie: **BN → Open Library → Google Books**. BN jest najlepsze
dla polskich książek (deskryptory, liczba stron), Open Library uzupełnia wydania
obcojęzyczne, Google Books dokłada opisy. Scalanie jest **per pole**: rekord z
wcześniejszego providera ma priorytet, a puste pola dopełniamy z kolejnych źródeł
(zob. :meth:`BookRecord.filled_from`).

ISBN jest walidowany **lokalnie przed** jakimkolwiek zapytaniem — błędny numer
nie generuje ruchu sieciowego.
"""

from __future__ import annotations

import logging

from epubforge.bookmeta._http import DEFAULT_TIMEOUT
from epubforge.bookmeta.isbn import validate_isbn
from epubforge.bookmeta.model import BookRecord
from epubforge.bookmeta.providers import (
    BNProvider,
    GoogleBooksProvider,
    OpenLibraryProvider,
    Provider,
)

logger = logging.getLogger(__name__)

# Domyślna kolejność providerów w łańcuchu (priorytet malejąco).
_DEFAULT_PROVIDERS: tuple[Provider, ...] = (
    BNProvider(),
    OpenLibraryProvider(),
    GoogleBooksProvider(),
)


def fetch_by_isbn(
    isbn: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    providers: tuple[Provider, ...] | None = None,
) -> BookRecord | None:
    """Pobiera metadane dla ISBN, scalając wyniki kolejnych providerów.

    Args:
        isbn: ISBN w dowolnym zapisie (z myślnikami/spacjami) — walidowany lokalnie.
        timeout: timeout pojedynczego zapytania (sekundy).
        providers: własna lista providerów (do testów); domyślnie BN → OL → GB.

    Returns:
        Scalony :class:`BookRecord` (pole ``isbn`` zawsze ustawione na wersję
        znormalizowaną) albo ``None``, gdy ISBN jest niepoprawny lub żadne źródło
        nie zwróciło danych.
    """
    normalized = validate_isbn(isbn)
    if normalized is None:
        logger.debug("Odrzucono niepoprawny ISBN (zero zapytań): %r", isbn)
        return None

    chain = providers if providers is not None else _DEFAULT_PROVIDERS
    merged: BookRecord | None = None
    for provider in chain:
        record = provider.fetch_by_isbn(normalized, timeout=timeout)
        if record is None:
            continue
        merged = record if merged is None else merged.filled_from(record)
        if _is_complete(merged):
            break

    if merged is not None:
        merged.isbn = normalized
    return merged


def _is_complete(record: BookRecord) -> bool:
    """Czy rekord jest na tyle kompletny, że nie warto odpytywać kolejnych źródeł."""
    return bool(
        record.title
        and record.creators
        and record.publisher
        and record.date
        and record.description
        and record.page_count is not None
    )
