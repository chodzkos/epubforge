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
from epubforge.bookmeta.match import rank_candidates
from epubforge.bookmeta.model import BookRecord, Candidate
from epubforge.bookmeta.providers import (
    BNProvider,
    GoogleBooksProvider,
    LubimyCzytacProvider,
    OpenLibraryProvider,
    Provider,
)

logger = logging.getLogger(__name__)

# Współdzielona instancja providera LC (wspólny cache + rate limiter): używana
# w łańcuchu po ISBN oraz w wyszukiwaniu kandydatów po tytule/autorze.
_LUBIMYCZYTAC = LubimyCzytacProvider()

# Domyślna kolejność providerów w łańcuchu (priorytet malejąco). LC po BN — daje
# opisy i cykle, których BN nie ma; OL/GB dopełniają wydania obce.
_DEFAULT_PROVIDERS: tuple[Provider, ...] = (
    BNProvider(),
    _LUBIMYCZYTAC,
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


def search_candidates(
    title: str,
    author: str = "",
    *,
    timeout: float = DEFAULT_TIMEOUT,
    provider: LubimyCzytacProvider | None = None,
) -> list[Candidate]:
    """Wyszukuje kandydatów po tytule/autorze (dla plików bez ISBN), z oceną dopasowania.

    Wynik jest posortowany malejąco po ``score`` (:mod:`epubforge.bookmeta.match`).
    **Nic nie jest wybierane automatycznie** — decyzję (nawet poniżej progu pewności)
    podejmuje użytkownik w GUI.

    Args:
        title: szukany tytuł.
        author: szukany autor (opcjonalny).
        timeout: timeout pojedynczego zapytania.
        provider: własny provider LC (do testów); domyślnie współdzielona instancja.

    Returns:
        Lista :class:`Candidate` z wypełnionym ``score`` (może być pusta).
    """
    source = provider if provider is not None else _LUBIMYCZYTAC
    if not title.strip():
        return []
    candidates = source.search_title_author(title, author, timeout=timeout)
    return rank_candidates(candidates, title, author)


def fetch_candidate(
    candidate: Candidate,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    provider: LubimyCzytacProvider | None = None,
) -> BookRecord | None:
    """Pobiera pełny :class:`BookRecord` dla wybranego kandydata (strona LC)."""
    source = provider if provider is not None else _LUBIMYCZYTAC
    return source.fetch_record(candidate.url, timeout=timeout)


def lubimyczytac_cache_hits() -> int:
    """Liczba trafień w cache współdzielonego providera LC (statystyka „z cache")."""
    return _LUBIMYCZYTAC.cache_hits()


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
