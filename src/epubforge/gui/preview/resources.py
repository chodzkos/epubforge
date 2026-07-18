"""Nieruchomy dostawca zasobów dla pojedynczej generacji podglądu."""

from __future__ import annotations

import hashlib
import posixpath
import zipfile
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Protocol
from urllib.parse import urlsplit

from epubforge.core import Epub
from epubforge.gui.preview.paths import UnsafePreviewPathError, normalize_internal_path

_SAFE_MIME: dict[str, str] = {
    ".css": "text/css",
    ".gif": "image/gif",
    ".htm": "text/html",
    ".html": "text/html",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".otf": "font/otf",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ttf": "font/ttf",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".xhtml": "application/xhtml+xml",
}

_SAFE_DECLARED_MIME = frozenset(_SAFE_MIME.values())


class ResourceProvider(Protocol):
    """Czysty kontrakt odczytu zasobów przez handler WebEngine."""

    def read(self, path: str, generation_id: int) -> bytes | None:
        """Zwraca bajty zasobu tylko dla właściwej generacji."""

    def media_type(self, path: str) -> str:
        """Zwraca typ z manifestu albo bezpieczny fallback rozszerzenia."""

    def exists(self, path: str) -> bool:
        """Czy zasób istniał w migawce generacji."""

    def revision(self, path: str) -> int:
        """Zwraca stabilną rewizję zasobu w tej migawce."""


class SnapshotResourceProvider:
    """Dostawca z zamrożonym overlayem, buforem Epub i indeksem oryginału.

    Nie przechowuje obiektu :class:`Epub` ani otwartego ZIP-a. Oryginał jest
    otwierany tylko na czas pojedynczego odczytu, więc zamknięcie sesji nie jest
    blokowane przez handler.
    """

    def __init__(
        self,
        source_path: Path,
        generation_id: int,
        *,
        dirty_overlay: Mapping[str, bytes],
        buffered: Mapping[str, bytes],
        deleted: frozenset[str],
        files: frozenset[str],
        manifest_types: Mapping[str, str],
        revisions: Mapping[str, int],
    ) -> None:
        self.source_path = Path(source_path)
        self.generation_id = generation_id
        self._source_signature = _source_signature(self.source_path)
        self._dirty = MappingProxyType(dict(dirty_overlay))
        self._buffered = MappingProxyType(dict(buffered))
        self._deleted = deleted
        self._files = files
        self._manifest_types = MappingProxyType(dict(manifest_types))
        self._revisions = MappingProxyType(dict(revisions))

    def read(self, path: str, generation_id: int) -> bytes | None:
        """Czyta overlay, potem bufor Epub, na końcu oryginalny wpis ZIP."""
        try:
            normalized = normalize_internal_path(path)
        except UnsafePreviewPathError:
            return None
        if generation_id != self.generation_id or normalized in self._deleted:
            return None
        if normalized in self._dirty:
            return self._dirty[normalized]
        if normalized in self._buffered:
            return self._buffered[normalized]
        if normalized not in self._files:
            return None
        if _source_signature(self.source_path) != self._source_signature:
            return None
        try:
            with zipfile.ZipFile(self.source_path) as archive:
                return archive.read(normalized)
        except (FileNotFoundError, KeyError, OSError, zipfile.BadZipFile):
            return None

    def media_type(self, path: str) -> str:
        """Preferuje manifest OPF; aktywnych typów nie zgaduje."""
        try:
            normalized = normalize_internal_path(path)
        except UnsafePreviewPathError:
            return "application/octet-stream"
        declared = self._manifest_types.get(normalized, "").strip().lower()
        if declared in _SAFE_DECLARED_MIME:
            return declared
        return _SAFE_MIME.get(posixpath.splitext(normalized)[1].lower(), "application/octet-stream")

    def exists(self, path: str) -> bool:
        """Sprawdza obecność bez odczytywania danych wpisu."""
        try:
            normalized = normalize_internal_path(path)
        except UnsafePreviewPathError:
            return False
        return normalized not in self._deleted and (
            normalized in self._dirty or normalized in self._buffered or normalized in self._files
        )

    def revision(self, path: str) -> int:
        """Zwraca rewizję lub zero dla nieznanego zasobu."""
        try:
            return self._revisions.get(normalize_internal_path(path), 0)
        except UnsafePreviewPathError:
            return 0


def create_resource_provider(
    epub: Epub,
    generation_id: int,
    dirty_overlay: Mapping[str, str | bytes],
) -> SnapshotResourceProvider:
    """Buduje nieruchomą migawkę logicznej zawartości otwartego EPUB-a."""
    dirty = {
        normalize_internal_path(path): value.encode("utf-8")
        if isinstance(value, str)
        else bytes(value)
        for path, value in dirty_overlay.items()
    }
    pending = epub.pending_changes()
    buffered = {
        normalize_internal_path(path): bytes(value) for path, value in pending.modified.items()
    }
    deleted = frozenset(normalize_internal_path(path) for path in pending.deleted)
    files = frozenset(normalize_internal_path(path) for path in epub.list_files())
    manifest_types = _manifest_media_types(epub)
    revisions = _resource_revisions(epub.path, files, buffered, dirty)
    return SnapshotResourceProvider(
        epub.path,
        generation_id,
        dirty_overlay=dirty,
        buffered=buffered,
        deleted=deleted,
        files=files,
        manifest_types=manifest_types,
        revisions=revisions,
    )


def _manifest_media_types(epub: Epub) -> dict[str, str]:
    """Mapuje href manifestu względem katalogu OPF na ścieżki archiwum."""
    result: dict[str, str] = {}
    base = epub.opf_dir()
    for item in epub.manifest:
        href = urlsplit(item.href)
        if href.scheme or href.netloc or href.query:
            continue
        try:
            path = normalize_internal_path(posixpath.join(base, href.path), percent_decode=True)
        except UnsafePreviewPathError:
            continue
        result[path] = item.media_type
    return result


def _resource_revisions(
    source: Path,
    files: frozenset[str],
    buffered: Mapping[str, bytes],
    dirty: Mapping[str, bytes],
) -> dict[str, int]:
    """Buduje tanie, stabilne rewizje: CRC ZIP lub skrót bajtów nakładki."""
    revisions: dict[str, int] = {}
    try:
        with zipfile.ZipFile(source) as archive:
            for path in files:
                try:
                    revisions[path] = archive.getinfo(path).CRC
                except KeyError:
                    continue
    except (FileNotFoundError, OSError, zipfile.BadZipFile):
        pass
    for mapping in (buffered, dirty):
        for path, value in mapping.items():
            digest = hashlib.blake2b(value, digest_size=8).digest()
            revisions[path] = int.from_bytes(digest, "big")
    return revisions


def _source_signature(path: Path) -> tuple[int, int, int, int] | None:
    """Identyfikuje wersję pliku źródłowego bez utrzymywania uchwytu."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
