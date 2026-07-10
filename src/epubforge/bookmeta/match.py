"""Dopasowanie książek po tytule i autorze (dla plików bez ISBN).

Gdy plik nie ma ISBN, kandydatów z wyszukiwarki providera trzeba ocenić względem
zapytania. Robimy to lokalnie i deterministycznie: normalizacja tekstu
(diakrytyki, wielkość liter, interpunkcja, podtytuł po ``:``) + podobieństwo
:class:`difflib.SequenceMatcher`. Zero nowych zależności.

Powyżej progu pewności (:data:`CONFIDENCE_THRESHOLD`) dopasowanie można uznać za
pewne; poniżej — decyzję zawsze podejmuje użytkownik (GUI), nigdy auto-zapis.
"""

from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher

from epubforge.bookmeta.model import Candidate

# Próg pewności dopasowania (0..1). Powyżej — kandydat może być uznany za trafny
# bez pytania; poniżej — wyłącznie ręczny wybór użytkownika.
CONFIDENCE_THRESHOLD = 0.85

# Waga tytułu i autora w łącznym wyniku. Tytuł jest silniejszym sygnałem;
# autora bierzemy pod uwagę tylko, gdy obie strony go podają.
_TITLE_WEIGHT = 0.7
_AUTHOR_WEIGHT = 0.3

# Litery, które NFKD nie rozkłada na „baza + diakrytyk" (nie mają wersji bazowej
# w Unicode), a które chcemy zredukować dla dopasowania — głównie polskie ``ł``.
_TRANSLITERATE = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D"})


def normalize(text: str) -> str:
    """Normalizuje tekst do porównania: bez diakrytyków, małe litery, bez interpunkcji.

    Kroki: odcięcie podtytułu po pierwszym ``:``; rozkład Unicode (NFKD) i usunięcie
    znaków łączących (diakrytyki); zamiana na małe litery; zamiana znaków niealfanumerycznych
    na spacje; sklejenie białych znaków.

    Args:
        text: dowolny łańcuch (tytuł lub nazwisko autora).

    Returns:
        Znormalizowana postać (może być pusta, gdy wejście było puste/interpunkcyjne).
    """
    without_subtitle = text.split(":", 1)[0].translate(_TRANSLITERATE)
    decomposed = unicodedata.normalize("NFKD", without_subtitle)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = stripped.lower()
    cleaned = "".join(ch if ch.isalnum() else " " for ch in lowered)
    return " ".join(cleaned.split())


def similarity(left: str, right: str) -> float:
    """Zwraca podobieństwo dwóch łańcuchów po normalizacji (0..1).

    Puste znormalizowane wejście po którejś stronie → 0.0 (brak sygnału).
    """
    a = normalize(left)
    b = normalize(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def score_candidate(candidate: Candidate, query_title: str, query_author: str) -> float:
    """Ocenia kandydata względem zapytania (tytuł + autor), zwraca wynik 0..1.

    Autora uwzględniamy tylko, gdy podano go w zapytaniu i u kandydata — inaczej
    wynik opiera się wyłącznie na tytule (waga autora nie „karze" braku danych).

    Args:
        candidate: kandydat z wyszukiwarki.
        query_title: tytuł, którego szukamy.
        query_author: autor, którego szukamy (może być pusty).

    Returns:
        Łączny wynik podobieństwa 0..1.
    """
    title_score = similarity(candidate.title, query_title)
    candidate_author = candidate.authors[0] if candidate.authors else ""
    if not query_author.strip() or not candidate_author:
        return title_score
    author_score = _best_author_similarity(candidate.authors, query_author)
    return _TITLE_WEIGHT * title_score + _AUTHOR_WEIGHT * author_score


def rank_candidates(
    candidates: list[Candidate], query_title: str, query_author: str
) -> list[Candidate]:
    """Zwraca kopie kandydatów z ustawionym ``score``, posortowane malejąco.

    Nie odrzuca kandydatów poniżej progu — decyzję zostawiamy użytkownikowi;
    próg (:data:`CONFIDENCE_THRESHOLD`) służy tylko do oznaczenia pewnych trafień.
    """
    scored: list[Candidate] = []
    for candidate in candidates:
        value = score_candidate(candidate, query_title, query_author)
        scored.append(
            Candidate(
                title=candidate.title,
                authors=list(candidate.authors),
                url=candidate.url,
                year=candidate.year,
                source=candidate.source,
                score=round(value, 4),
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored


def _best_author_similarity(candidate_authors: list[str], query_author: str) -> float:
    """Najlepsze podobieństwo autora zapytania do któregokolwiek autora kandydata."""
    return max((similarity(author, query_author) for author in candidate_authors), default=0.0)
