"""Model danych warstwy metadanych — dataclass :class:`BookRecord`.

:class:`BookRecord` jest **supersetem** :class:`epubforge.core.Metadata`: dokłada
pola, których nie ma w Dublin Core EPUB-a, a które zwracają zewnętrzne katalogi —
przede wszystkim ``page_count`` (liczba stron wydania papierowego) oraz ``source``
(z którego providera pochodzi rekord). Podpakiet ``bookmeta`` jest celowo
niezależny od reszty projektu (zero importów z ``gui``/``core``) — kandydat do
późniejszej ekstrakcji jako osobna biblioteka.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields


@dataclass
class BookRecord:
    """Rekord metadanych książki pobrany z zewnętrznego katalogu.

    Attributes:
        title: tytuł książki.
        creators: autorzy w kolejności występowania.
        publisher: wydawca.
        date: data/rok publikacji (tekst, np. ``"2014"`` lub ISO ``"2014-05-01"``).
        description: opis/streszczenie (BN zwykle go nie ma → dopełnia GB).
        language: kod języka ISO 639-1 (np. ``pl``) lub pusty.
        isbn: znormalizowany ISBN, którego dotyczy rekord.
        page_count: liczba stron wydania papierowego lub ``None``.
        subjects: tematy/deskryptory przedmiotowe (surowe stringi).
        series: nazwa cyklu/serii lub pusty łańcuch.
        source: identyfikator providera źródłowego (``bn``/``openlibrary``/``googlebooks``).
    """

    title: str = ""
    creators: list[str] = field(default_factory=list)
    publisher: str = ""
    date: str = ""
    description: str = ""
    language: str = ""
    isbn: str = ""
    page_count: int | None = None
    subjects: list[str] = field(default_factory=list)
    series: str = ""
    source: str = ""

    def is_empty(self) -> bool:
        """Czy rekord nie niesie żadnej użytecznej wartości (same domyślne pola)."""
        return not any(
            (
                self.title,
                self.creators,
                self.publisher,
                self.date,
                self.description,
                self.language,
                self.page_count is not None,
                self.subjects,
                self.series,
            )
        )

    def filled_from(self, other: BookRecord) -> BookRecord:
        """Zwraca nowy rekord z pustymi polami dopełnionymi z ``other``.

        Wartości już obecne w ``self`` mają priorytet (są źródłem prawdy dla pola);
        z ``other`` bierzemy tylko to, czego u nas brakuje. Zasada „dopełniaj puste"
        dotyczy każdego pola z osobna — pola-listy traktujemy jako całość (pusta
        lista = brak), więc np. deskryptory BN nie mieszają się z generycznymi
        kategoriami Google Books, gdy BN już coś dostarczyło.

        Args:
            other: rekord z kolejnego (mniej priorytetowego) providera.

        Returns:
            Nowy scalony :class:`BookRecord` (argumenty pozostają nietknięte).
        """
        merged = BookRecord(**{f.name: getattr(self, f.name) for f in fields(self)})
        for name in ("title", "publisher", "date", "description", "language", "series"):
            if not getattr(merged, name) and getattr(other, name):
                setattr(merged, name, getattr(other, name))
        if not merged.creators and other.creators:
            merged.creators = list(other.creators)
        if not merged.subjects and other.subjects:
            merged.subjects = list(other.subjects)
        if merged.page_count is None and other.page_count is not None:
            merged.page_count = other.page_count
        if not merged.source:
            merged.source = other.source
        return merged
