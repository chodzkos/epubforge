"""Własne wyjątki biblioteki core.

Hierarchia: wszystkie dziedziczą po `EpubError`, dzięki czemu kod kliencki
może łapać `EpubError` ogólnie albo konkretny podtyp precyzyjnie.
"""

from __future__ import annotations


class EpubError(Exception):
    """Bazowy wyjątek dla wszystkich operacji na plikach EPUB."""


class InvalidEpubError(EpubError):
    """Plik nie istnieje lub nie jest poprawnym archiwum ZIP/EPUB."""


class EpubNotOpenError(EpubError):
    """Operacja wymaga otwartego EPUB-a.

    Wywołaj :meth:`Epub.open` albo użyj klasy jako context managera
    (``with Epub(path) as epub: ...``) przed odczytem/zapisem.
    """


class OpfNotFoundError(EpubError):
    """Nie udało się ustalić ścieżki OPF.

    Najczęściej oznacza brak lub uszkodzony ``META-INF/container.xml``
    (plik, z którego odczytujemy lokalizację pliku OPF — nie zgadujemy jej).
    """


class ConversionError(EpubError):
    """Konwersja pliku nie powiodła się."""


class ConverterNotFoundError(ConversionError):
    """Wymagany zewnętrzny konwerter nie został znaleziony."""
