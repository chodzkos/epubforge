"""Bezpieczny tokenizer kandydatów atrybutu HTML ``srcset``."""

from __future__ import annotations

import math

_ASCII_WHITESPACE = frozenset("\t\n\f\r ")


def parse_srcset(source: str) -> list[tuple[str, str]] | None:
    """Tokenizuje URL oraz opcjonalny dodatni deskryptor ``w`` lub ``x``."""
    candidates: list[tuple[str, str]] = []
    index = 0
    length = len(source)
    while index < length:
        while index < length and source[index] in _ASCII_WHITESPACE:
            index += 1
        if index >= length or source[index] == ",":
            return None
        start = index
        while index < length and source[index] not in _ASCII_WHITESPACE:
            index += 1
        url = source[start:index]
        trailing_commas = len(url) - len(url.rstrip(","))
        if trailing_commas:
            if trailing_commas != 1:
                return None
            url = url[:-1]
            descriptor = ""
        else:
            while index < length and source[index] in _ASCII_WHITESPACE:
                index += 1
            start = index
            while index < length and source[index] != ",":
                index += 1
            descriptor = source[start:index].strip()
            if index < length:
                index += 1
        if not url or not _valid_descriptor(descriptor):
            return None
        candidates.append((url, descriptor))
    return candidates or None


def _valid_descriptor(descriptor: str) -> bool:
    """Akceptuje brak deskryptora, dodatnią szerokość ``w`` albo gęstość ``x``."""
    if not descriptor:
        return True
    if any(character in _ASCII_WHITESPACE for character in descriptor):
        return False
    value, suffix = descriptor[:-1], descriptor[-1:].lower()
    if suffix == "w":
        return value.isascii() and value.isdecimal() and int(value) > 0
    if suffix == "x":
        try:
            density = float(value)
        except ValueError:
            return False
        return math.isfinite(density) and density > 0
    return False
