"""Własne wyjątki biblioteki core.

Hierarchia: wszystkie dziedziczą po `EpubError`, dzięki czemu kod kliencki
może łapać `EpubError` ogólnie albo konkretny podtyp precyzyjnie.
"""

from __future__ import annotations


class EpubError(Exception):
    """Bazowy wyjątek dla wszystkich operacji na plikach EPUB."""


class InvalidEpubError(EpubError):
    """Plik nie istnieje lub nie jest poprawnym archiwum ZIP/EPUB."""


class ResourceLimitError(EpubError):
    """EPUB albo jego struktura przekracza bezpieczny budżet zasobów.

    Zgłaszane m.in. przed kosztowną dekompresją na podstawie metadanych ZIP oraz
    podczas budowania i przetwarzania ograniczonych struktur, takich jak spis
    treści. Obejmuje zbyt wiele wpisów, nadmierną głębokość, rozmiary i stopień
    kompresji, a także niekanoniczne nazwy członków archiwum. Komunikat jest
    bezpieczny do pokazania w GUI/CLI.
    """


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


class ValidationError(EpubError):
    """Walidacja EPUB nie mogła zostać przeprowadzona.

    Dotyczy sytuacji technicznych (brak/zepsuty raport JSON, timeout, brak
    narzędzi), a NIE samego wyniku „EPUB jest niepoprawny" — ten wraca jako
    :class:`~epubforge.validators.ValidationReport` z ``valid=False``.
    """


class ConversionError(EpubError):
    """Konwersja pliku nie powiodła się."""


class ConverterNotFoundError(ConversionError):
    """Wymagany zewnętrzny konwerter nie został znaleziony."""


class InvalidPublicationHrefError(EpubError):
    """Publication href nie da się bezpiecznie zredukować do wpisu ZIP."""


class MissingPublicationMemberError(EpubError):
    """Manifest wskazuje zasób, którego nie ma w archiwum EPUB."""


class AmbiguousPublicationMemberError(EpubError):
    """Żądana ścieżka pasuje do więcej niż jednego wpisu po normalizacji NFC.

    Exact match zawsze wygrywa. Ten błąd oznacza brak exact identity przy
    co najmniej dwóch równoważnych nazwach (np. NFC i NFD). Nie wolno
    wybierać pierwszego wpisu.
    """
