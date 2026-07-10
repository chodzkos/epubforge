"""Wspólne wykrywanie plików fontów w EPUB-ie (współdzielone przez fixery).

Wydzielone z ``css_fixer`` (usuwanie fontów) i używane też przez ``fonts``
(subsetting), żeby logika rozpoznawania fontów żyła w jednym miejscu.
"""

from __future__ import annotations

import posixpath
from pathlib import Path
from urllib.parse import unquote, urldefrag

from epubforge.core import Epub, ManifestItem

FONT_MEDIA_TYPES = {
    "application/font-sfnt",
    "application/font-woff",
    "application/vnd.ms-opentype",
    "application/x-font-otf",
    "application/x-font-ttf",
    "font/otf",
    "font/sfnt",
    "font/ttf",
    "font/woff",
    "font/woff2",
}
FONT_SUFFIXES = {".otf", ".ttf", ".woff", ".woff2"}


def href_suffix(href: str) -> str:
    """Zwraca rozszerzenie ``href`` (małymi literami) bez fragmentu URL."""
    path, _fragment = urldefrag(href)
    return Path(path).suffix.lower()


def manifest_path(epub: Epub, item: ManifestItem) -> str:
    """Rozwiązuje ``manifest href`` względem katalogu OPF na ścieżkę w archiwum."""
    href, _fragment = urldefrag(item.href)
    href = unquote(href)
    if href.startswith("/"):
        return posixpath.normpath(href.lstrip("/"))
    base = epub.opf_dir()
    if not base:
        return posixpath.normpath(href)
    return posixpath.normpath(posixpath.join(base, href))


def font_files(epub: Epub) -> list[str]:
    """Zwraca posortowane wewnętrzne ścieżki plików fontów (manifest + archiwum)."""
    manifest_paths = [
        manifest_path(epub, item)
        for item in epub.manifest
        if item.media_type in FONT_MEDIA_TYPES or href_suffix(item.href) in FONT_SUFFIXES
    ]
    archive_paths = [
        name for name in epub.list_files() if Path(name).suffix.lower() in FONT_SUFFIXES
    ]
    return sorted(set(manifest_paths + archive_paths))
