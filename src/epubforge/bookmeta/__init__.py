"""Warstwa pobierania metadanych książek z zewnętrznych katalogów (opt-in).

Samodzielny podpakiet — **zero importów z ``gui``**, minimalne z ``core`` — kandydat
do późniejszej ekstrakcji jako osobna biblioteka (wzorzec ``chodzkos-gui-kit``).
Publiczne API:

* :func:`fetch_by_isbn` — pobierz i scal metadane z łańcucha BN → LC → OL → GB;
* :func:`search_candidates` — wyszukaj kandydatów po tytule/autorze (bez ISBN);
* :func:`fetch_candidate` — pobierz pełny rekord wybranego kandydata;
* :func:`validate_isbn` / :func:`extract_isbn_from_epub` — walidacja i ekstrakcja ISBN;
* :class:`BookRecord` / :class:`Candidate` — rekord metadanych i wynik wyszukiwania.

Cały ruch sieciowy przechodzi przez :mod:`epubforge.bookmeta._http` (utwardzony:
wyłącznie https z walidacją hosta/portu/braku userinfo, blokada SSRF po DNS —
loopback/prywatne/link-local/reserved, walidacja KAŻDEGO przekierowania z limitem
liczby hopów, opcjonalny pin hostów per provider, twardy timeout, odrzucanie
odpowiedzi ponad ``MAX_BYTES``, każdy błąd → ``None``). Provider LubimyCzytac
akceptuje wyłącznie WŁASNE URL-e (host LC lub link względny). Scraping LC jest
dodatkowo grzecznościowy: cache + rate limiter (:mod:`epubforge.bookmeta.cache`).
"""

from epubforge.bookmeta.ai import PRESETS, AIConfig, AIError
from epubforge.bookmeta.chain import fetch_by_isbn, fetch_candidate, search_candidates
from epubforge.bookmeta.isbn import extract_isbn_from_epub, validate_isbn
from epubforge.bookmeta.model import BookRecord, Candidate
from epubforge.bookmeta.tagging import (
    MERGE_POLICIES,
    TaggingResult,
    TagProposal,
    apply_policy,
    extract_content_sample,
    suggest_tags_cascade,
)
from epubforge.bookmeta.taxonomy import Taxonomy, load_taxonomy, map_subjects

__all__ = [
    "MERGE_POLICIES",
    "PRESETS",
    "AIConfig",
    "AIError",
    "BookRecord",
    "Candidate",
    "TagProposal",
    "TaggingResult",
    "Taxonomy",
    "apply_policy",
    "extract_content_sample",
    "extract_isbn_from_epub",
    "fetch_by_isbn",
    "fetch_candidate",
    "load_taxonomy",
    "map_subjects",
    "search_candidates",
    "suggest_tags_cascade",
    "validate_isbn",
]
