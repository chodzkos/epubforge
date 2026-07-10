"""Warstwa pobierania metadanych książek z zewnętrznych katalogów (opt-in).

Samodzielny podpakiet — **zero importów z ``gui``**, minimalne z ``core`` — kandydat
do późniejszej ekstrakcji jako osobna biblioteka (wzorzec ``chodzkos-gui-kit``).
Publiczne API:

* :func:`fetch_by_isbn` — pobierz i scal metadane z łańcucha BN → OL → GB;
* :func:`validate_isbn` — lokalna walidacja/normalizacja ISBN (przed zapytaniem);
* :class:`BookRecord` — rekord metadanych (superset Dublin Core).

Cały ruch sieciowy przechodzi przez :mod:`epubforge.bookmeta._http` (tylko https,
twardy timeout, limit rozmiaru odpowiedzi, każdy błąd → ``None``).
"""

from epubforge.bookmeta.chain import fetch_by_isbn
from epubforge.bookmeta.isbn import validate_isbn
from epubforge.bookmeta.model import BookRecord

__all__ = [
    "BookRecord",
    "fetch_by_isbn",
    "validate_isbn",
]
