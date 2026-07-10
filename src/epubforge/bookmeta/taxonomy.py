"""Taksonomia tagów po polsku — mapowanie surowych tematów na kanoniczne tagi.

Deterministyczna warstwa tagowania (bez AI): deskryptory BN i kategorie LC/GB są
sprowadzane do jednego zbioru kanonicznych tagów PL wg pliku ``taxonomy_pl.toml``
(cztery kategorie: gatunek, epoka, miejsce, tematy). Dopasowanie jest odporne na
wielkość liter i diakrytyki (porównanie po normalizacji), a synonimy zwijają
warianty do jednego kanonu (``sci-fi`` = ``SF`` → ``science fiction``).

Plik użytkownika w katalogu konfiguracji ma **pierwszeństwo** nad wbudowanym.
"""

from __future__ import annotations

import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover — tylko Python 3.10
    import tomli as tomllib

from epubforge.core.config import config_dir

# Kategorie taksonomii w kolejności priorytetu przy limicie tagów.
CATEGORIES: tuple[str, ...] = ("gatunek", "epoka", "miejsce", "tematy")
# Priorytet kategorii przy limicie: gatunek → epoka/miejsce → tematy.
_CATEGORY_PRIORITY = {"gatunek": 0, "epoka": 1, "miejsce": 1, "tematy": 2}
# Maksymalna liczba tagów w wyniku (wg celu etapu).
MAX_TAGS = 10
# Nazwa pliku taksonomii (wbudowany i użytkownika mają tę samą nazwę).
_TAXONOMY_FILE = "taxonomy_pl.toml"
# Litery bez rozkładu NFKD, które redukujemy ręcznie (głównie polskie ``ł``).
_TRANSLITERATE = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O"})


@dataclass(frozen=True)
class TagEntry:
    """Kanoniczny tag taksonomii wraz z jego kategorią."""

    tag: str
    category: str


@dataclass(frozen=True)
class MappedTag:
    """Tag zmapowany na taksonomię (kanoniczna nazwa + kategoria)."""

    tag: str
    category: str


@dataclass
class MappedTags:
    """Wynik mapowania surowych tematów.

    Attributes:
        mapped: tagi rozpoznane w taksonomii (zdeduplikowane, w kolejności napotkania).
        unmapped: surowe tematy bez odpowiednika w taksonomii (propozycje „poza taksonomią").
    """

    mapped: list[MappedTag] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)


@dataclass
class Taxonomy:
    """Załadowana taksonomia z indeksem dopasowań.

    ``lookup`` mapuje znormalizowany wariant (tag/synonim/mapowanie źródła) na wpis;
    ``entries`` trzyma kanoniczne tagi w kolejności wczytania (kolejność w pliku).
    """

    entries: list[TagEntry]
    lookup: dict[str, TagEntry]

    def canonical_tags(self, category: str | None = None) -> list[str]:
        """Zwraca kanoniczne tagi (opcjonalnie tylko z jednej kategorii)."""
        return [e.tag for e in self.entries if category is None or e.category == category]

    def match(self, raw: str) -> TagEntry | None:
        """Dopasowuje surowy temat do kanonicznego wpisu (po normalizacji) lub ``None``."""
        return self.lookup.get(_normalize(raw))

    def resolve_canonical(self, tag: str, category: str | None = None) -> str | None:
        """Zwraca kanoniczną nazwę tagu, jeśli należy do taksonomii (i danej kategorii).

        Używane do walidacji odpowiedzi AI: akceptujemy też synonim (mapowany na
        kanon), a tag spoza listy → ``None`` (odrzucony).
        """
        entry = self.lookup.get(_normalize(tag))
        if entry is None:
            return None
        if category is not None and entry.category != category:
            return None
        return entry.tag


def load_taxonomy(path: Path | None = None) -> Taxonomy:
    """Wczytuje taksonomię z TOML (użytkownika, jeśli jest; inaczej wbudowaną).

    Args:
        path: jawna ścieżka do pliku (pomija rozwiązywanie); głównie do testów.

    Returns:
        Zbudowana :class:`Taxonomy` z indeksem dopasowań.
    """
    toml_path = path if path is not None else _resolve_path()
    with open(toml_path, "rb") as handle:
        data = tomllib.load(handle)

    entries: list[TagEntry] = []
    lookup: dict[str, TagEntry] = {}
    for category in CATEGORIES:
        for item in data.get(category, []):
            if not isinstance(item, dict):
                continue
            tag = item.get("tag")
            if not isinstance(tag, str) or not tag.strip():
                continue
            entry = TagEntry(tag=tag.strip(), category=category)
            entries.append(entry)
            variants = [tag, *_str_list(item.get("synonyms")), *_str_list(item.get("maps"))]
            for variant in variants:
                key = _normalize(variant)
                if key:
                    lookup.setdefault(key, entry)
    return Taxonomy(entries=entries, lookup=lookup)


def map_subjects(raw: list[str], taxonomy: Taxonomy) -> MappedTags:
    """Mapuje surowe tematy (deskryptory BN, kategorie LC/GB) na taksonomię.

    Zmapowane tagi są deduplikowane po kanonicznej nazwie; tematy bez odpowiednika
    trafiają do ``unmapped`` jako propozycje „poza taksonomią".
    """
    result = MappedTags()
    seen: set[str] = set()
    for subject in raw:
        entry = taxonomy.match(subject)
        if entry is None:
            cleaned = " ".join(subject.split())
            if cleaned and cleaned not in result.unmapped:
                result.unmapped.append(cleaned)
            continue
        if entry.tag not in seen:
            seen.add(entry.tag)
            result.mapped.append(MappedTag(tag=entry.tag, category=entry.category))
    return result


def limit_tags(tags: list[MappedTag], limit: int = MAX_TAGS) -> list[MappedTag]:
    """Ogranicza liczbę tagów z priorytetem gatunek → epoka/miejsce → tematy.

    Sortowanie jest stabilne, więc w obrębie tego samego priorytetu zachowana jest
    kolejność napotkania.
    """
    ordered = sorted(tags, key=lambda t: _CATEGORY_PRIORITY.get(t.category, 99))
    return ordered[:limit]


def _resolve_path() -> Path:
    """Zwraca ścieżkę pliku taksonomii: użytkownika (jeśli istnieje) lub wbudowaną."""
    user = config_dir() / _TAXONOMY_FILE
    if user.is_file():
        return user
    return _builtin_dir() / _TAXONOMY_FILE


def _builtin_dir() -> Path:
    """Katalog wbudowanych danych (także w bundlu PyInstaller)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "epubforge" / "data"
    return Path(__file__).resolve().parent.parent / "data"


def _str_list(value: object) -> list[str]:
    """Zwraca listę stringów z pola TOML (toleruje brak/nie-listę)."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _normalize(text: str) -> str:
    """Normalizuje tekst do dopasowania: bez diakrytyków, małe litery, bez interpunkcji."""
    translated = text.translate(_TRANSLITERATE)
    decomposed = unicodedata.normalize("NFKD", translated)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = "".join(ch if ch.isalnum() else " " for ch in stripped.lower())
    return " ".join(cleaned.split())
