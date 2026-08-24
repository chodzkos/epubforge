"""Czyste narzędzia tekstowe (bez Qt): dekodowanie i pozycje znakowe.

Warstwa ``core`` — używana zarówno przez ``core.search`` jak i przez warstwę GUI
(``gui.editor_files`` re-eksportuje te funkcje). Trzymanie ich tu zamiast w GUI
pozwala ``core`` korzystać z nich bez łamania zasady zależności (``core`` nie
importuje z ``gui``).
"""

from __future__ import annotations

from epubforge.core.publication_href import resolve_from_directory

# Znak zastępczy Unicode wstawiany przez ``bytes.decode(errors="replace")``.
REPLACEMENT_CHAR = "�"


def decode_text(data: bytes) -> tuple[str, bool]:
    """Dekoduje bajty jako UTF-8 z podmianą; zwraca ``(tekst, czy_były_zastępcze)``."""
    text = data.decode("utf-8", errors="replace")
    return text, REPLACEMENT_CHAR in text


def offset_to_line_col(text: str, offset: int) -> tuple[int, int]:
    """Zamienia pozycję znakową na ``(linia, kolumna)`` — obie liczone od 1."""
    clamped = max(0, min(offset, len(text)))
    prefix = text[:clamped]
    line = prefix.count("\n") + 1
    col = clamped - (prefix.rfind("\n") + 1) + 1
    return line, col


def line_col_to_offset(text: str, line: int, col: int) -> int:
    """Zamienia ``(linia, kolumna)`` (od 1) na pozycję znakową (clamp do długości)."""
    lines = text.split("\n")
    target = max(1, min(line, len(lines)))
    offset = sum(len(lines[i]) + 1 for i in range(target - 1))
    return min(offset + max(0, col - 1), len(text))


def resolve_internal_path(href: str, opf_dir: str) -> str:
    """Rozwiązuje ``href`` manifestu (względem katalogu OPF) do ścieżki w archiwum.

    Thin wrapper nad :func:`epubforge.core.publication_href.resolve_publication_member`.
    """
    return resolve_from_directory(opf_dir, href)
