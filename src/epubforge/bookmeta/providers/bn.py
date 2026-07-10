"""Provider Biblioteki Narodowej (``data.bn.org.pl``) — najlepsze źródło dla PL.

Oficjalne API BN jest darmowe, bez klucza i bez limitów; zwraca pełny rekord
MARC 21. Dla polskich książek to najbogatsze źródło: wydawca, rok, liczba stron
i — co unikalne — **deskryptory przedmiotowe BN** (gotowe tagi: postacie,
miejsca, gatunki, tematy) oznaczone w rekordzie jako ``$2 = DBN``.

Parsujemy rekord MARC, a nie „wygodne" pola najwyższego poziomu odpowiedzi —
te ostatnie sklejają kilka podpól w jeden łańcuch (np. ``author`` powtarza autora
i wydawcę), więc są zawodne. MARC daje dostęp do konkretnych podpól.

Wszystkie odczyty są **defensywne**: brak pola / nieoczekiwany kształt → wartość
pusta, nigdy wyjątek.
"""

from __future__ import annotations

import re
from typing import Any

from epubforge.bookmeta._http import DEFAULT_TIMEOUT, fetch_json
from epubforge.bookmeta._lang import to_iso639_1
from epubforge.bookmeta.model import BookRecord

_API_URL = "https://data.bn.org.pl/api/institutions/bibs.json"

# Pola MARC 6XX niosące tematy/deskryptory (osobowe, korporatywne, geograficzne,
# chronologiczne, przedmiotowe, gatunkowe). Bierzemy z nich deskryptory BN.
_SUBJECT_TAGS = frozenset({"600", "610", "611", "630", "648", "650", "651", "655", "658", "662"})


class BNProvider:
    """Źródło metadanych: API Biblioteki Narodowej."""

    name = "bn"

    def fetch_by_isbn(self, isbn: str, *, timeout: float = DEFAULT_TIMEOUT) -> BookRecord | None:
        """Pobiera i parsuje rekord BN dla ISBN (``None`` przy braku/błędzie)."""
        url = f"{_API_URL}?isbnIssn={isbn}&limit=1"
        data = fetch_json(url, timeout=timeout)
        return _parse_response(data, isbn)


def _parse_response(data: Any, isbn: str) -> BookRecord | None:
    """Buduje :class:`BookRecord` z odpowiedzi API BN (pierwszy pasujący rekord)."""
    if not isinstance(data, dict):
        return None
    bibs = data.get("bibs")
    if not isinstance(bibs, list) or not bibs:
        return None
    bib = bibs[0]
    if not isinstance(bib, dict):
        return None
    marc = bib.get("marc")
    fields = marc.get("fields") if isinstance(marc, dict) else None
    if not isinstance(fields, list):
        return None

    record = BookRecord(
        title=_title(fields),
        creators=_creators(fields),
        publisher=_publisher(fields),
        date=_date(fields, bib),
        language=_language(fields),
        isbn=isbn,
        page_count=_page_count(fields),
        subjects=_subjects(fields),
        series=_series(fields),
        description=_strip(_first_subfield(fields, "520", "a")),
        source="bn",
    )
    return None if record.is_empty() else record


# ── Ekstrakcja pól ──────────────────────────────────────────────────────────────


def _title(fields: list[Any]) -> str:
    """Składa tytuł z MARC 245: ``$a`` + opcjonalny podtytuł ``$b``."""
    main = _strip(_first_subfield(fields, "245", "a"))
    sub = _strip(_first_subfield(fields, "245", "b"))
    if main and sub:
        return f"{main}: {sub}"
    return main or sub


def _creators(fields: list[Any]) -> list[str]:
    """Zwraca autorów: MARC 100 ``$a`` (główny) + wszystkie 700 ``$a`` (współautorzy)."""
    creators: list[str] = []
    for tag in ("100", "700"):
        for field_value in _iter_fields(fields, tag):
            name = _strip(_subfield(field_value, "a"))
            if name and name not in creators:
                creators.append(name)
    return creators


def _publisher(fields: list[Any]) -> str:
    """Zwraca wydawcę z MARC 264 ``$b`` (nowszy standard RDA) lub 260 ``$b``."""
    return _strip(_first_subfield(fields, "264", "b") or _first_subfield(fields, "260", "b"))


def _date(fields: list[Any], bib: dict[str, Any]) -> str:
    """Zwraca rok publikacji: czyste pole najwyższego poziomu lub rok z MARC 264/260 ``$c``."""
    year = bib.get("publicationYear")
    if isinstance(year, str) and re.fullmatch(r"\d{4}", year.strip()):
        return year.strip()
    raw = _first_subfield(fields, "264", "c") or _first_subfield(fields, "260", "c")
    match = re.search(r"\d{4}", raw)
    return match.group(0) if match else ""


def _language(fields: list[Any]) -> str:
    """Zwraca kod języka ISO 639-1 z MARC 008 (pozycje 35-37) lub 041 ``$a``."""
    control = _first_control(fields, "008")
    if len(control) >= 38:
        mapped = to_iso639_1(control[35:38])
        if mapped:
            return mapped
    return to_iso639_1(_first_subfield(fields, "041", "a"))


def _page_count(fields: list[Any]) -> int | None:
    """Wyciąga liczbę stron z MARC 300 ``$a`` (np. ``"330, [6] stron"`` → 330)."""
    raw = _first_subfield(fields, "300", "a")
    match = re.search(r"\d+", raw)
    return int(match.group(0)) if match else None


def _series(fields: list[Any]) -> str:
    """Zwraca nazwę cyklu z MARC 490/830 ``$a`` (bez części autorskiej po ``/``)."""
    raw = _first_subfield(fields, "490", "a") or _first_subfield(fields, "830", "a")
    return _strip(raw.split("/", 1)[0]) if raw else ""


def _subjects(fields: list[Any]) -> list[str]:
    """Zbiera deskryptory przedmiotowe BN (pola 6XX z ``$2 = DBN``), po ``$a``."""
    subjects: list[str] = []
    for field_obj in fields:
        if not isinstance(field_obj, dict):
            continue
        for tag, value in field_obj.items():
            if tag in _SUBJECT_TAGS and _is_dbn(value):
                descriptor = _strip(_subfield(value, "a"))
                if descriptor and descriptor not in subjects:
                    subjects.append(descriptor)
    return subjects


# ── Niskopoziomowe pomocniki MARC ────────────────────────────────────────────────


def _iter_fields(fields: list[Any], tag: str) -> list[dict[str, Any]]:
    """Zwraca wartości wszystkich pól MARC o danym tagu (mogą się powtarzać)."""
    result: list[dict[str, Any]] = []
    for field_obj in fields:
        if isinstance(field_obj, dict):
            value = field_obj.get(tag)
            if isinstance(value, dict):
                result.append(value)
    return result


def _first_control(fields: list[Any], tag: str) -> str:
    """Zwraca wartość pierwszego pola kontrolnego (00X) — to zwykły string, nie dict."""
    for field_obj in fields:
        if isinstance(field_obj, dict):
            value = field_obj.get(tag)
            if isinstance(value, str):
                return value
    return ""


def _subfield(field_value: dict[str, Any], code: str) -> str:
    """Zwraca pierwsze podpole o danym kodzie z wartości pola MARC danych."""
    subfields = field_value.get("subfields")
    if not isinstance(subfields, list):
        return ""
    for sub in subfields:
        if isinstance(sub, dict) and code in sub:
            return str(sub[code])
    return ""


def _first_subfield(fields: list[Any], tag: str, code: str) -> str:
    """Zwraca podpole ``code`` z pierwszego pola ``tag``, które je zawiera."""
    for field_value in _iter_fields(fields, tag):
        value = _subfield(field_value, code)
        if value:
            return value
    return ""


def _is_dbn(field_value: dict[str, Any]) -> bool:
    """Czy pole tematyczne pochodzi ze słownika deskryptorów BN (``$2 = DBN``)."""
    subfields = field_value.get("subfields")
    if not isinstance(subfields, list):
        return False
    return any(isinstance(sub, dict) and sub.get("2") == "DBN" for sub in subfields)


def _strip(value: str) -> str:
    """Ucina spacje i końcową interpunkcję ISBD (``/ : ; , .``) z pola MARC."""
    return value.strip().rstrip("/:;,. ").strip()
