"""Warstwa pobierania metadanych książek z zewnętrznych katalogów (opt-in).

Samodzielny podpakiet — **zero importów z ``gui``**, minimalne z ``core`` — kandydat
do późniejszej ekstrakcji jako osobna biblioteka (wzorzec ``chodzkos-gui-kit``).
Publiczne API:

* :func:`fetch_by_isbn` — pobierz i scal metadane z łańcucha BN → LC → OL → GB;
* :func:`search_candidates` — wyszukaj kandydatów po tytule/autorze (bez ISBN);
* :func:`fetch_candidate` — pobierz pełny rekord wybranego kandydata;
* :func:`validate_isbn` / :func:`extract_isbn_from_epub` — walidacja i ekstrakcja ISBN;
* :class:`BookRecord` / :class:`Candidate` — rekord metadanych i wynik wyszukiwania.

Cały ruch sieciowy przechodzi przez :mod:`epubforge.bookmeta._http` (tylko https,
twardy timeout, limit rozmiaru odpowiedzi, każdy błąd → ``None``). Scraping LC jest
dodatkowo grzecznościowy: cache + rate limiter (:mod:`epubforge.bookmeta.cache`).
"""

from epubforge.bookmeta.chain import fetch_by_isbn, fetch_candidate, search_candidates
from epubforge.bookmeta.isbn import extract_isbn_from_epub, validate_isbn
from epubforge.bookmeta.model import BookRecord, Candidate

__all__ = [
    "BookRecord",
    "Candidate",
    "extract_isbn_from_epub",
    "fetch_by_isbn",
    "fetch_candidate",
    "search_candidates",
    "validate_isbn",
]
