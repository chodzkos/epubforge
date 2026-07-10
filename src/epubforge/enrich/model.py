"""Model danych hurtowego wzbogacania metadanych (:mod:`epubforge.enrich`).

Definiuje polityki scalania (``fill``/``append``/``overwrite``), mapowanie nazw pól
z CLI na atrybuty :class:`~epubforge.core.Metadata`, oraz struktury wyniku per
książka i podsumowania. Logika (obliczanie planu zmian) mieszka w
:mod:`epubforge.enrich.engine`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Polityki scalania wartości ze źródła z istniejącymi metadanymi.
POLICIES: tuple[str, ...] = ("fill", "append", "overwrite")
# Domyślne polityki w hurcie: pola tylko uzupełniamy, tagi dopisujemy — nic nie
# znika bez jawnej decyzji (``overwrite`` wyłącznie wprost).
DEFAULT_FIELD_POLICY = "fill"
DEFAULT_TAGS_POLICY = "append"

# Aliasy nazw pól z CLI (po polsku i po angielsku) → atrybut Metadata.
FIELD_ALIASES: dict[str, str] = {
    "tytuł": "title",
    "tytul": "title",
    "title": "title",
    "autorzy": "creators",
    "autor": "creators",
    "creators": "creators",
    "język": "language",
    "jezyk": "language",
    "language": "language",
    "wydawca": "publisher",
    "publisher": "publisher",
    "data": "date",
    "date": "date",
    "opis": "description",
    "description": "description",
    "cykl": "series",
    "seria": "series",
    "series": "series",
    "isbn": "identifier",
    "identyfikator": "identifier",
    "identifier": "identifier",
    "strony": "page_count",
    "pages": "page_count",
}
# Domyślny zestaw pól, gdy ``--fields`` pominięto.
DEFAULT_FIELDS: tuple[str, ...] = (
    "title",
    "creators",
    "publisher",
    "date",
    "description",
    "language",
    "series",
    "page_count",
)
# Pola wielowartościowe (listy) — polityki traktują je inaczej niż skalary.
LIST_FIELDS: frozenset[str] = frozenset({"creators"})
# Umowna nazwa „pola" tagów w raporcie zmian.
TAGS_FIELD = "tags"

# Rodzaje dopasowania książki do rekordu.
MATCH_ISBN = "isbn"
MATCH_FUZZY = "fuzzy"
MATCH_NONE = "brak"

# Akcje na pojedynczym polu.
ACTION_CHANGED = "changed"
ACTION_SKIPPED = "skipped"


@dataclass(frozen=True)
class FieldChange:
    """Opis planowanej zmiany jednego pola (do raportu i podglądu dry-run).

    Attributes:
        field: nazwa pola (atrybut Metadata lub ``tags``).
        old: dotychczasowa wartość (tekstowo, do wyświetlenia).
        new: nowa wartość (tekstowo).
        action: :data:`ACTION_CHANGED` lub :data:`ACTION_SKIPPED`.
    """

    field: str
    old: str
    new: str
    action: str


def normalize_fields(raw: list[str]) -> tuple[str, ...]:
    """Mapuje nazwy pól z CLI na atrybuty Metadata (nieznane pomija).

    Args:
        raw: nazwy pól podane przez użytkownika (np. ``["tytuł", "opis"]``).

    Returns:
        Krotka rozpoznanych atrybutów (bez duplikatów, w kolejności podania).
    """
    result: list[str] = []
    for name in raw:
        attr = FIELD_ALIASES.get(name.strip().lower())
        if attr is not None and attr not in result:
            result.append(attr)
    return tuple(result)


@dataclass
class EnrichOptions:
    """Parametry wzbogacania (te same dla plików i biblioteki Calibre).

    Attributes:
        fields: pola do wzbogacenia (atrybuty Metadata).
        want_tags: czy uzupełniać tagi (``dc:subject``) z taksonomii.
        field_policy: polityka dla pól skalarnych/list.
        tags_policy: polityka dla tagów.
        dry_run: gdy ``True`` — tylko plan, zero zapisów.
    """

    fields: tuple[str, ...] = DEFAULT_FIELDS
    want_tags: bool = False
    field_policy: str = DEFAULT_FIELD_POLICY
    tags_policy: str = DEFAULT_TAGS_POLICY
    dry_run: bool = False


@dataclass
class BookOutcome:
    """Wynik wzbogacenia jednej książki (do raportu).

    Attributes:
        identifier: ścieżka pliku EPUB albo ``id`` w bibliotece Calibre.
        match: rodzaj dopasowania (:data:`MATCH_ISBN`/:data:`MATCH_FUZZY`/:data:`MATCH_NONE`).
        source: provider źródłowy rekordu (``bn``/``lubimyczytac``/…), pusty gdy brak.
        changed: nazwy pól, które zostałyby/zostały zmienione.
        skipped: nazwy pól pominiętych (polityka lub brak danych).
        from_cache: czy pobranie skorzystało z cache (LC).
        error: komunikat błędu (pusty, gdy OK).
    """

    identifier: str
    match: str
    source: str = ""
    changed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    from_cache: bool = False
    error: str = ""

    @property
    def found(self) -> bool:
        """Czy udało się dopasować rekord (jakiekolwiek źródło)."""
        return self.match != MATCH_NONE and not self.error


@dataclass
class EnrichSummary:
    """Zbiorcze podsumowanie przebiegu wzbogacania."""

    total: int = 0
    found: int = 0
    not_found: int = 0
    from_cache: int = 0
    errors: int = 0
    changed: int = 0

    @classmethod
    def from_outcomes(cls, outcomes: list[BookOutcome]) -> EnrichSummary:
        """Buduje podsumowanie z listy wyników per książka."""
        summary = cls(total=len(outcomes))
        for outcome in outcomes:
            if outcome.error:
                summary.errors += 1
            if outcome.found:
                summary.found += 1
            else:
                summary.not_found += 1
            if outcome.from_cache:
                summary.from_cache += 1
            if outcome.changed:
                summary.changed += 1
        return summary
