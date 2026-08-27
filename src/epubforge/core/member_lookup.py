"""Lookup wpisów EPUB z exact-first i jednoznacznym fallbackiem Unicode NFC.

Warstwa tożsamości nazw ZIP — nie mylić z ``posixpath.normpath`` ani z polityką
traversal z :mod:`epubforge.core.publication_href`.

Kontrakt:

1. Exact string match wygrywa.
2. Gdy exact nie istnieje, szukamy nazw o tym samym ``unicodedata.normalize("NFC")``.
3. Dokładnie jeden równoważny wpis → zwracamy jego rzeczywistą nazwę.
4. Dwa lub więcej → :class:`AmbiguousPublicationMemberError` (bez arbitralnego wyboru).
5. Zero → ``KeyError``, jak przy zwykłym braku wpisu.

Nie przepisujemy całej publikacji na NFC. Nie odrzucamy książki z parą NFC/NFD.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Collection, Iterable, Set

from epubforge.core.exceptions import AmbiguousPublicationMemberError


def nfc_identity(name: str) -> str:
    """Zwraca postać NFC nazwy — tylko klucz porównania, nie nowa nazwa wpisu."""
    return unicodedata.normalize("NFC", name)


def live_archive_members(
    zip_names: Iterable[str],
    modified: Iterable[str],
    deleted: Set[str],
) -> set[str]:
    """Żywe tożsamości: katalog ZIP i overlay minus exact deleted."""
    names = {name for name in zip_names if name not in deleted}
    names.update(name for name in modified if name not in deleted)
    return names


def locate_archive_member(requested: str, names: Collection[str]) -> str:
    """Zwraca rzeczywistą nazwę wpisu dla żądanej ścieżki.

    Raises:
        KeyError: brak exact i brak jednoznacznego równoważnika NFC.
        AmbiguousPublicationMemberError: kilka równoważników bez exact match.
    """
    pool: Collection[str] = names if isinstance(names, (set, frozenset)) else set(names)
    if requested in pool:
        return requested
    target = nfc_identity(requested)
    matches = [name for name in pool if nfc_identity(name) == target]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise KeyError(requested)
    raise AmbiguousPublicationMemberError(
        f"Niejednoznaczna nazwa wpisu publikacji (NFC/NFD): {requested!r} → {sorted(matches)!r}."
    )
