"""Kontrakt providera metadanych (:class:`Provider`).

Provider to źródło danych o książce (katalog biblioteczny, księgarnia API…).
Kontrakt jest celowo minimalny i **defensywny**: metoda zwraca ``None`` zamiast
rzucać wyjątki — łańcuch (:mod:`epubforge.bookmeta.chain`) po prostu przechodzi
do kolejnego źródła.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from epubforge.bookmeta._http import DEFAULT_TIMEOUT
from epubforge.bookmeta.model import BookRecord


@runtime_checkable
class Provider(Protocol):
    """Interfejs pojedynczego źródła metadanych po ISBN.

    Attributes:
        name: krótki identyfikator providera (trafia do ``BookRecord.source``).
    """

    name: str

    def fetch_by_isbn(self, isbn: str, *, timeout: float = DEFAULT_TIMEOUT) -> BookRecord | None:
        """Pobiera rekord dla znormalizowanego ISBN albo ``None``.

        Args:
            isbn: **już zwalidowany** ISBN (10 lub 13 znaków; walidację robi łańcuch).
            timeout: maksymalny czas pojedynczego zapytania w sekundach.

        Returns:
            :class:`BookRecord` z wypełnionymi polami albo ``None`` (brak wyniku,
            błąd sieci/HTTP, timeout). Implementacja **nie może** rzucać wyjątku.
        """
        ...
