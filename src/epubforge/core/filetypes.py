"""Klasyfikacja typów plików wewnątrz EPUB-a (bez Qt).

Warstwa ``core`` — czyste funkcje operujące na ścieżkach POSIX i media-type z
manifestu. Trzymanie ich tu zamiast w GUI pozwala CLI (``cli/_batch.py``,
diff dry-run) klasyfikować wpisy bez importowania PySide6, a jednocześnie nie
łamie zasady zależności (``core`` nie importuje z ``gui``). Warstwa GUI
re-eksportuje te symbole z :mod:`epubforge.gui.editor_files` — istniejące
importy ``from epubforge.gui.editor_files import ...`` działają bez zmian.
"""

from __future__ import annotations

import posixpath
from typing import Literal

# Profil podświetlania składni edytora.
Profile = Literal["xml", "css"]

# Klucze grup w drzewie (etykiety lokalizuje zakładka GUI przez ``_()``).
GROUP_TEXT = "text"
GROUP_STYLE = "style"
GROUP_IMAGE = "image"
GROUP_FONT = "font"
GROUP_OTHER = "other"

# Kolejność grup w drzewie.
GROUP_ORDER = (GROUP_TEXT, GROUP_STYLE, GROUP_IMAGE, GROUP_FONT, GROUP_OTHER)

# Profile podświetlania składni edytora.
PROFILE_XML: Profile = "xml"
PROFILE_CSS: Profile = "css"

_TEXT_SUFFIXES = {".xhtml", ".html", ".htm", ".xml", ".opf", ".ncx", ".txt", ".svg"}
_XML_SUFFIXES = {".xhtml", ".html", ".htm", ".xml", ".opf", ".ncx", ".svg"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_FONT_SUFFIXES = {".otf", ".ttf", ".woff", ".woff2"}

_FONT_MEDIA_PREFIXES = ("font/", "application/font-", "application/x-font-")
_FONT_MEDIA_TYPES = {
    "application/vnd.ms-opentype",
    "application/x-font-otf",
    "application/x-font-ttf",
}
_XML_MEDIA_TYPES = {
    "application/xhtml+xml",
    "text/html",
    "application/xml",
    "text/xml",
    "application/oebps-package+xml",
    "application/x-dtbncx+xml",
    "image/svg+xml",
}


def classify(internal_path: str, media_type: str | None = None) -> str:
    """Zwraca klucz grupy pliku (``text``/``style``/``image``/``font``/``other``).

    Najpierw bierze pod uwagę ``media_type`` z manifestu, a w razie braku — sufiks
    ścieżki (dla plików spoza manifestu zwróconych przez ``list_files()``).
    """
    suffix = _suffix(internal_path)
    mt = (media_type or "").lower()

    if mt == "text/css" or suffix == ".css":
        return GROUP_STYLE
    if _is_font(mt, suffix):
        return GROUP_FONT
    # SVG to XML (edytowalny) — traktujemy jako tekst, nie obraz rastrowy.
    if mt == "image/svg+xml" or suffix == ".svg":
        return GROUP_TEXT
    if mt.startswith("image/") or suffix in _IMAGE_SUFFIXES:
        return GROUP_IMAGE
    if mt in _XML_MEDIA_TYPES or mt.startswith("text/") or suffix in _TEXT_SUFFIXES:
        return GROUP_TEXT
    return GROUP_OTHER


def profile_for(internal_path: str, media_type: str | None = None) -> Profile | None:
    """Zwraca profil podświetlania (``xml``/``css``) albo ``None`` (bez edytora)."""
    suffix = _suffix(internal_path)
    mt = (media_type or "").lower()
    if mt == "text/css" or suffix == ".css":
        return PROFILE_CSS
    if mt in _XML_MEDIA_TYPES or suffix in _XML_SUFFIXES:
        return PROFILE_XML
    return None


def is_editable(internal_path: str, media_type: str | None = None) -> bool:
    """Czy plik nadaje się do edycji tekstowej (ma profil podświetlania)."""
    return profile_for(internal_path, media_type) is not None


def is_image(internal_path: str, media_type: str | None = None) -> bool:
    """Czy plik to obraz rastrowy (podgląd przez QPixmap)."""
    return classify(internal_path, media_type) == GROUP_IMAGE


def is_html(internal_path: str, media_type: str | None = None) -> bool:
    """Czy plik to dokument (X)HTML — kwalifikuje się do przybliżonego podglądu.

    Wyłącza generyczny XML (OPF/NCX) i SVG — podgląd HTML dotyczy treści rozdziałów.
    """
    suffix = _suffix(internal_path)
    mt = (media_type or "").lower()
    return mt in {"text/html", "application/xhtml+xml"} or suffix in {".xhtml", ".html", ".htm"}


def _suffix(internal_path: str) -> str:
    """Małe rozszerzenie pliku z wewnętrznej ścieżki POSIX."""
    return posixpath.splitext(internal_path)[1].lower()


def _is_font(media_type: str, suffix: str) -> bool:
    """Czy wpis to font (po media-type lub rozszerzeniu)."""
    if suffix in _FONT_SUFFIXES or media_type in _FONT_MEDIA_TYPES:
        return True
    return any(media_type.startswith(prefix) for prefix in _FONT_MEDIA_PREFIXES)
