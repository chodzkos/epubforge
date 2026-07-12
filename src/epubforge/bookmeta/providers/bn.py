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

import json
import re
from typing import Any
from urllib.parse import quote_plus

from epubforge.bookmeta._http import DEFAULT_TIMEOUT, fetch_json
from epubforge.bookmeta._lang import to_iso639_1
from epubforge.bookmeta.cache import DEFAULT_TTL_SECONDS, MetadataCache, RateLimiter
from epubforge.bookmeta.match import CONFIDENCE_THRESHOLD, score_candidate
from epubforge.bookmeta.model import BookRecord, Candidate

_API_URL = "https://data.bn.org.pl/api/institutions/bibs.json"

# Pola MARC 6XX niosące tematy/deskryptory (osobowe, korporatywne, geograficzne,
# chronologiczne, przedmiotowe, gatunkowe). Bierzemy z nich deskryptory BN.
_SUBJECT_TAGS = frozenset({"600", "610", "611", "630", "648", "650", "651", "655", "658", "662"})

# Odstęp między żądaniami do BN. API jest darmowe i bez limitów, ale zachowujemy
# grzecznościowy odstęp (lżejszy niż scraping LC). Fallback tytułowy = drugie żądanie
# = drugi odstęp — akceptowalne, bo cache czyni ponowienia tanimi.
_MIN_INTERVAL_SECONDS = 1.0
# Ilu kandydatów pobrać przy wyszukiwaniu po tytule (do fuzzy dopasowania).
_TITLE_LIMIT = 5


class BNProvider:
    """Źródło metadanych: API Biblioteki Narodowej — z fallbackiem tytułowym.

    E-booki mają **własny ISBN wydania elektronicznego**, a katalog BN indeksuje głównie
    wydania papierowe — ISBN z pliku często nie ma rekordu w BN, choć książka (papierowa)
    tam jest. Dlatego wyszukiwanie jest **dwustopniowe**:

    1. zapytanie po ISBN — trafienie → zwracamy (``match_type="isbn"``);
    2. przy pudle, jeśli znany jest tytuł (i opcjonalnie autor), zapytanie po tytule i
       **fuzzy dopasowanie** przez :mod:`epubforge.bookmeta.match`; pewne trafienie →
       zwracamy z ``match_type="fuzzy"``.

    **ISBN pliku NIE jest nadpisywany** ISBN-em papierowym z BN — zwracamy tylko metadane
    bibliograficzne (tytuł, autor, rok, wydawca, opis, deskryptory), a pole ``isbn`` rekordu
    pozostaje ISBN-em e-wydania z pliku.

    Oba żądania idą przez ten sam cache i rate limiter; klucz cache to URL, więc zapytania
    po ISBN i po tytule są rozróżnione (nie kolidują).
    """

    name = "bn"

    def __init__(
        self,
        *,
        cache: MetadataCache | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        """Args:
        cache: cache odpowiedzi; ``None`` = leniwie utworzony w katalogu configu.
        rate_limiter: limiter żądań; ``None`` = domyślny (min. odstęp :data:`_MIN_INTERVAL_SECONDS`).
        """
        self._cache = cache
        self._rate_limiter = (
            rate_limiter if rate_limiter is not None else RateLimiter(_MIN_INTERVAL_SECONDS)
        )

    def fetch_by_isbn(
        self,
        isbn: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        title: str = "",
        author: str = "",
    ) -> BookRecord | None:
        """Pobiera rekord BN: najpierw po ISBN, a przy pudle — po tytule (fuzzy).

        Args:
            isbn: znormalizowany ISBN (e-wydania z pliku).
            timeout: timeout pojedynczego zapytania.
            title: tytuł z metadanych EPUB — użyty do fallbacku, gdy ISBN nie trafia.
            author: autor z metadanych EPUB — wzmacnia fuzzy dopasowanie (opcjonalny).

        Returns:
            :class:`BookRecord` (``match_type`` ``"isbn"`` lub ``"fuzzy"``) albo ``None``.
        """
        url = f"{_API_URL}?isbnIssn={isbn}&limit=1"
        record = _parse_response(self._get_json(url, timeout=timeout), isbn)
        if record is not None:
            return record
        if not title.strip():
            return None
        return self._by_title(isbn, title, author, timeout=timeout)

    # ── Fallback tytułowy ────────────────────────────────────────────────────────

    def _by_title(self, isbn: str, title: str, author: str, *, timeout: float) -> BookRecord | None:
        """Wyszukuje po tytule i zwraca pewne fuzzy trafienie (albo ``None``)."""
        url = f"{_API_URL}?title={quote_plus(title)}&limit={_TITLE_LIMIT}"
        data = self._get_json(url, timeout=timeout)
        best_fields: list[Any] | None = None
        best_bib: dict[str, Any] = {}
        best_score = 0.0
        for bib, fields in _iter_bibs(data):
            candidate = Candidate(
                title=_title(fields), authors=_creators(fields), year=_date(fields, bib)
            )
            score = score_candidate(candidate, title, author)
            if score > best_score:
                best_fields, best_bib, best_score = fields, bib, score
        if best_fields is None or best_score < CONFIDENCE_THRESHOLD:
            return None
        return _record_from_fields(best_fields, best_bib, isbn, match_type="fuzzy")

    # ── Warstwa sieciowa (cache + rate limiter) ──────────────────────────────────

    def _get_json(self, url: str, *, timeout: float) -> Any | None:
        """Zwraca JSON: z cache albo pobrany (z rate limitem) i zbuforowany.

        Klucz cache to URL, więc zapytania po ISBN i po tytule są rozróżnione.
        """
        cache = self._ensure_cache()
        cached = cache.get(self.name, url, ttl_seconds=DEFAULT_TTL_SECONDS)
        if cached is not None:
            try:
                return json.loads(cached)
            except (json.JSONDecodeError, ValueError):
                return None
        self._rate_limiter.wait()
        data = fetch_json(url, timeout=timeout)
        if data is None:
            return None
        cache.set(self.name, url, json.dumps(data))
        return data

    def _ensure_cache(self) -> MetadataCache:
        """Leniwie tworzy domyślny cache w katalogu configu (bez side-effectów przy imporcie)."""
        if self._cache is None:
            from epubforge.core.config import config_dir

            self._cache = MetadataCache(config_dir() / "bookmeta_cache.sqlite")
        return self._cache


def _iter_bibs(data: Any) -> list[tuple[dict[str, Any], list[Any]]]:
    """Rozwija odpowiedź BN do listy par (bib, pola MARC); pomija rekordy bez MARC."""
    if not isinstance(data, dict):
        return []
    bibs = data.get("bibs")
    if not isinstance(bibs, list):
        return []
    result: list[tuple[dict[str, Any], list[Any]]] = []
    for bib in bibs:
        if not isinstance(bib, dict):
            continue
        marc = bib.get("marc")
        fields = marc.get("fields") if isinstance(marc, dict) else None
        if isinstance(fields, list):
            result.append((bib, fields))
    return result


def _record_from_fields(
    fields: list[Any], bib: dict[str, Any], isbn: str, *, match_type: str = "isbn"
) -> BookRecord | None:
    """Buduje :class:`BookRecord` z pól MARC pojedynczego rekordu (``None``, gdy pusty)."""
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
        match_type=match_type,
    )
    return None if record.is_empty() else record


def _parse_response(data: Any, isbn: str) -> BookRecord | None:
    """Buduje :class:`BookRecord` z odpowiedzi API BN (pierwszy pasujący rekord, po ISBN)."""
    bibs = _iter_bibs(data)
    if not bibs:
        return None
    bib, fields = bibs[0]
    return _record_from_fields(fields, bib, isbn, match_type="isbn")


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
