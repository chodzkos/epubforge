"""Czysta logika edytora EPUB: klasyfikacja plików, profil, dekodowanie, pozycje.

Funkcje są wolne od Qt (operują na stringach/ścieżkach) — dzięki temu da się je
testować bez ``QApplication``. Widgety i zakładka importują je i ubierają w UI.

Wszystkie symbole mieszkają teraz w warstwie ``core`` (:mod:`epubforge.core.filetypes`
i :mod:`epubforge.core.textutil`) — moduł zostaje jako zgodny re-eksport, żeby
istniejące importy ``from epubforge.gui.editor_files import ...`` działały bez zmian
i żeby CLI/core mogły klasyfikować wpisy bez ładowania PySide6.
"""

from __future__ import annotations

# Klasyfikacja typów plików (grupy, profile, predykaty) mieszka w ``core``.
from epubforge.core.filetypes import (
    GROUP_FONT,
    GROUP_IMAGE,
    GROUP_ORDER,
    GROUP_OTHER,
    GROUP_STYLE,
    GROUP_TEXT,
    PROFILE_CSS,
    PROFILE_XML,
    Profile,
    classify,
    is_editable,
    is_html,
    is_image,
    profile_for,
)

# Czyste helpery tekstowe (dekodowanie, pozycje, ścieżki) mieszkają w ``core``.
from epubforge.core.textutil import (
    decode_text,
    line_col_to_offset,
    offset_to_line_col,
    resolve_internal_path,
)

__all__ = [
    "GROUP_FONT",
    "GROUP_IMAGE",
    "GROUP_ORDER",
    "GROUP_OTHER",
    "GROUP_STYLE",
    "GROUP_TEXT",
    "PROFILE_CSS",
    "PROFILE_XML",
    "Profile",
    "classify",
    "decode_text",
    "is_editable",
    "is_html",
    "is_image",
    "line_col_to_offset",
    "offset_to_line_col",
    "profile_for",
    "resolve_internal_path",
]
