"""Walidacja i normalizacja numerów ISBN.

Walidacja jest **lokalna i darmowa** — odbywa się przed jakimkolwiek zapytaniem
sieciowym, żeby błędny ISBN (literówka, zła suma kontrolna) nie generował ruchu
do zewnętrznych API. Obsługiwane są oba formaty: ISBN-10 (z cyfrą kontrolną
``0-9`` lub ``X``) i ISBN-13 (13 cyfr, suma kontrolna EAN-13).

Moduł potrafi też **wydobyć ISBN z treści EPUB-a** (:func:`extract_isbn_from_epub`)
— przydatne dla plików bez ISBN w metadanych: strona redakcyjna z numerem żyje
zwykle w pierwszych dokumentach spine.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from epubforge.core.exceptions import InvalidPublicationHrefError
from epubforge.core.publication_href import resolve_from_directory

if TYPE_CHECKING:
    from epubforge.core.epub import Epub

# Kandydat na ISBN w tekście: opcjonalny prefiks 978/979, dziewięć cyfr (z możliwymi
# łącznikami/spacjami) i cyfra kontrolna. Granice zapobiegają wycinaniu fragmentu
# dłuższej liczby. Ostateczną poprawność rozstrzyga :func:`validate_isbn` (suma kontrolna).
_ISBN_IN_TEXT_RE = re.compile(r"(?<![\d\-])(?:97[89][-\s]?)?(?:\d[-\s]?){9}[\dxX](?![\d\-])")


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


def extract_isbn_from_epub(epub: Epub, max_docs: int = 5) -> str | None:
    """Wyszukuje ISBN w pierwszych dokumentach spine EPUB-a (strona redakcyjna).

    Przechodzi po maksymalnie ``max_docs`` pierwszych dokumentach z kolejności
    czytania (spine), przeszukując ich tekst wzorcem ISBN i weryfikując sumę
    kontrolną. Zwraca pierwszy poprawny ISBN albo ``None``. Odczyt jest defensywny:
    brakujący/niedostępny dokument jest pomijany, nie przerywa wyszukiwania.

    Args:
        epub: **otwarty** obiekt :class:`~epubforge.core.epub.Epub`.
        max_docs: ile pierwszych dokumentów spine przejrzeć.

    Returns:
        Znormalizowany ISBN albo ``None``, gdy nie znaleziono.
    """
    manifest_by_id = {item.id: item for item in epub.manifest}
    opf_dir = epub.opf_dir()
    for idref in epub.spine[:max_docs]:
        item = manifest_by_id.get(idref)
        if item is None:
            continue
        try:
            internal = resolve_from_directory(opf_dir, item.href)
            data = epub.read_file(internal)
        except (InvalidPublicationHrefError, KeyError, OSError):
            continue
        found = _find_isbn_in_text(data.decode("utf-8", "replace"))
        if found is not None:
            return found
    return None


def _find_isbn_in_text(text: str) -> str | None:
    """Zwraca pierwszy poprawny (suma kontrolna) ISBN znaleziony w tekście lub ``None``."""
    for match in _ISBN_IN_TEXT_RE.finditer(text):
        candidate = validate_isbn(match.group(0))
        if candidate is not None:
            return candidate
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
