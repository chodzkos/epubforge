"""Walidacja i normalizacja numerów ISBN.

Walidacja jest **lokalna i darmowa** — odbywa się przed jakimkolwiek zapytaniem
sieciowym, żeby błędny ISBN (literówka, zła suma kontrolna) nie generował ruchu
do zewnętrznych API. Obsługiwane są oba formaty: ISBN-10 (z cyfrą kontrolną
``0-9`` lub ``X``) i ISBN-13 (13 cyfr, suma kontrolna EAN-13).
"""

from __future__ import annotations


def validate_isbn(text: str) -> str | None:
    """Waliduje i normalizuje ISBN, zwracając czystą postać albo ``None``.

    Z wejścia usuwane są separatory (myślniki, spacje) i typowe prefiksy
    (``ISBN``, ``urn:isbn:``) — zostają wyłącznie cyfry oraz ewentualne końcowe
    ``X`` (cyfra kontrolna ISBN-10). Wynik jest zwracany tylko wtedy, gdy długość
    i suma kontrolna są poprawne.

    Args:
        text: dowolny łańcuch mogący zawierać ISBN.

    Returns:
        Znormalizowany ISBN (10 lub 13 znaków, wielkie ``X``) albo ``None``, gdy
        wejście nie jest poprawnym ISBN-em.
    """
    normalized = _normalize(text)
    if len(normalized) == 10 and _is_valid_isbn10(normalized):
        return normalized
    if len(normalized) == 13 and _is_valid_isbn13(normalized):
        return normalized
    return None


def _normalize(text: str) -> str:
    """Zostawia wyłącznie cyfry i ``X`` z wejścia (wielkimi literami)."""
    return "".join(ch for ch in text.upper() if ch.isdigit() or ch == "X")


def _is_valid_isbn10(isbn: str) -> bool:
    """Sprawdza sumę kontrolną ISBN-10 (ważona 10..1, modulo 11, ``X`` = 10)."""
    total = 0
    for index, char in enumerate(isbn):
        if char == "X":
            # ``X`` (=10) dozwolone wyłącznie na ostatniej pozycji.
            if index != 9:
                return False
            value = 10
        elif char.isdigit():
            value = int(char)
        else:
            return False
        total += value * (10 - index)
    return total % 11 == 0


def _is_valid_isbn13(isbn: str) -> bool:
    """Sprawdza sumę kontrolną ISBN-13 (wagi 1/3 naprzemiennie, modulo 10)."""
    if not isbn.isdigit():
        return False
    total = sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(isbn))
    return total % 10 == 0
