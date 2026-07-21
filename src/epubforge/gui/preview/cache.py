"""Ograniczony bajtowo cache zasobów podglądu, współdzielony przez generacje."""

from __future__ import annotations

import posixpath
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from threading import RLock


class ResourceKind(str, Enum):
    """Klasa zasobu mająca osobny budżet pamięci."""

    DOCUMENT = "documents"
    CSS = "css"
    IMAGE = "images"
    FONT = "fonts"
    OTHER = "other"


@dataclass(frozen=True)
class CacheLimits:
    """Budżety cache; suma kategorii jest twardym limitem globalnym."""

    documents: int = 4 * 1024 * 1024
    css: int = 2 * 1024 * 1024
    images: int = 24 * 1024 * 1024
    fonts: int = 16 * 1024 * 1024
    other: int = 2 * 1024 * 1024

    @property
    def total(self) -> int:
        return self.documents + self.css + self.images + self.fonts + self.other

    def for_kind(self, kind: ResourceKind) -> int:
        return int(getattr(self, kind.value))


@dataclass(frozen=True)
class CacheStats:
    """Nieruchomy licznik pamięci i trafień cache."""

    entries: int
    bytes: int
    hits: int
    misses: int
    evictions: int
    by_kind: dict[str, int]
    limits: CacheLimits


CacheKey = tuple[str, int]


class ResourceByteCache:
    """Wątkowo bezpieczny LRU z osobnym limitem dla każdej klasy zasobu."""

    def __init__(self, limits: CacheLimits | None = None) -> None:
        self.limits = limits or CacheLimits()
        self._items: dict[ResourceKind, OrderedDict[CacheKey, bytes]] = {
            kind: OrderedDict() for kind in ResourceKind
        }
        self._bytes: dict[ResourceKind, int] = dict.fromkeys(ResourceKind, 0)
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._lock = RLock()

    def get(self, path: str, revision: int, kind: ResourceKind) -> bytes | None:
        """Zwraca wartość i przesuwa ją na koniec kolejki LRU."""
        key = (path, revision)
        with self._lock:
            value = self._items[kind].get(key)
            if value is None:
                self._misses += 1
                return None
            self._items[kind].move_to_end(key)
            self._hits += 1
            return value

    def put(self, path: str, revision: int, kind: ResourceKind, data: bytes) -> bool:
        """Dodaje dane, o ile pojedynczy zasób mieści się w budżecie kategorii."""
        size = len(data)
        limit = self.limits.for_kind(kind)
        if size > limit:
            return False
        key = (path, revision)
        with self._lock:
            items = self._items[kind]
            previous = items.pop(key, None)
            if previous is not None:
                self._bytes[kind] -= len(previous)
            while items and self._bytes[kind] + size > limit:
                _old_key, old = items.popitem(last=False)
                self._bytes[kind] -= len(old)
                self._evictions += 1
            items[key] = bytes(data)
            self._bytes[kind] += size
        return True

    def invalidate(self, path: str, *, keep_revision: int | None = None) -> None:
        """Usuwa wyłącznie rewizje wskazanego zasobu, pozostawiając opcjonalnie bieżącą."""
        with self._lock:
            for kind, items in self._items.items():
                stale = [key for key in items if key[0] == path and key[1] != keep_revision]
                for key in stale:
                    self._bytes[kind] -= len(items.pop(key))

    def clear(self) -> None:
        """Czyści dane i liczniki bez zmiany skonfigurowanych limitów."""
        with self._lock:
            for items in self._items.values():
                items.clear()
            self._bytes = dict.fromkeys(ResourceKind, 0)
            self._hits = self._misses = self._evictions = 0

    def remaining(self, kind: ResourceKind) -> int:
        """Zwraca wolny budżet kategorii bez zmiany kolejności LRU."""
        with self._lock:
            return self.limits.for_kind(kind) - self._bytes[kind]

    def stats(self) -> CacheStats:
        """Zwraca spójny snapshot liczników."""
        with self._lock:
            by_kind = {kind.value: self._bytes[kind] for kind in ResourceKind}
            return CacheStats(
                entries=sum(len(items) for items in self._items.values()),
                bytes=sum(by_kind.values()),
                hits=self._hits,
                misses=self._misses,
                evictions=self._evictions,
                by_kind=by_kind,
                limits=self.limits,
            )


def resource_kind(path: str, media_type: str = "") -> ResourceKind:
    """Klasyfikuje zasób po bezpiecznym MIME, a pomocniczo po rozszerzeniu."""
    mime = media_type.lower()
    suffix = posixpath.splitext(path)[1].lower()
    if mime == "text/css" or suffix == ".css":
        return ResourceKind.CSS
    if mime.startswith("image/") or suffix in {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}:
        return ResourceKind.IMAGE
    if mime.startswith("font/") or suffix in {".otf", ".ttf", ".woff", ".woff2"}:
        return ResourceKind.FONT
    if mime in {"application/xhtml+xml", "text/html"} or suffix in {".htm", ".html", ".xhtml"}:
        return ResourceKind.DOCUMENT
    return ResourceKind.OTHER
