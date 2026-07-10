"""Testy dopasowania po tytule/autorze (:mod:`epubforge.bookmeta.match`)."""

from __future__ import annotations

import pytest

from epubforge.bookmeta.match import (
    CONFIDENCE_THRESHOLD,
    normalize,
    rank_candidates,
    score_candidate,
    similarity,
)
from epubforge.bookmeta.model import Candidate


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Wiedźmin", "wiedzmin"),  # diakrytyki usunięte
        ("ŻÓŁĆ", "zolc"),
        ("Ostatnie życzenie: opowiadania", "ostatnie zyczenie"),  # podtytuł po ':' odcięty
        ("  Wielkie   ODSTĘPY  ", "wielkie odstepy"),  # białe znaki + wielkość liter
        ("!@#$%", ""),  # sama interpunkcja → pusto
    ],
)
def test_normalize(text: str, expected: str) -> None:
    """normalize usuwa diakrytyki, interpunkcję, podtytuł i sprowadza do małych liter."""
    assert normalize(text) == expected


def test_similarity_identical_after_normalization() -> None:
    """Teksty różniące się tylko diakrytykami/wielkością są maksymalnie podobne."""
    assert similarity("Wiedźmin", "wiedzmin") == 1.0


def test_similarity_empty_is_zero() -> None:
    """Puste znormalizowane wejście → brak sygnału (0.0)."""
    assert similarity("", "cokolwiek") == 0.0
    assert similarity("!!!", "tytuł") == 0.0


def test_score_candidate_uses_title_when_no_author() -> None:
    """Bez autora w zapytaniu wynik zależy wyłącznie od tytułu."""
    candidate = Candidate(title="Ostatnie życzenie", authors=["Andrzej Sapkowski"])
    assert score_candidate(candidate, "Ostatnie życzenie", "") == 1.0


def test_score_candidate_combines_title_and_author() -> None:
    """Zgodny tytuł + zgodny autor → pełny wynik; zły autor obniża wynik."""
    candidate = Candidate(title="Ostatnie życzenie", authors=["Andrzej Sapkowski"])
    good = score_candidate(candidate, "Ostatnie życzenie", "Sapkowski Andrzej")
    bad = score_candidate(candidate, "Ostatnie życzenie", "Stephen King")
    assert good > bad
    assert good >= CONFIDENCE_THRESHOLD


def test_rank_candidates_sorts_by_score() -> None:
    """rank_candidates ustawia score i sortuje malejąco, nie mutując wejścia."""
    candidates = [
        Candidate(title="Zupełnie inna książka", authors=["X"]),
        Candidate(title="Ostatnie życzenie", authors=["Andrzej Sapkowski"]),
    ]
    ranked = rank_candidates(candidates, "Ostatnie życzenie", "Andrzej Sapkowski")
    assert ranked[0].title == "Ostatnie życzenie"
    assert ranked[0].score > ranked[1].score
    # wejście nietknięte (score domyślnie 0.0)
    assert candidates[0].score == 0.0
