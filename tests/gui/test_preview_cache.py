"""Regresje poprawności i złożoności cache zasobów podglądu."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterator, Mapping
from pathlib import Path

from epubforge.gui.preview.cache import CacheKey, CacheLimits, ResourceByteCache, ResourceKind
from epubforge.gui.preview.resources import SnapshotResourceProvider


class CountingOrderedDict(OrderedDict[CacheKey, bytes]):
    """OrderedDict z deterministycznym licznikiem iterowanych kluczy."""

    key_yields = 0

    def __iter__(self) -> Iterator[CacheKey]:
        for key in super().__iter__():
            type(self).key_yields += 1
            yield key


def _entries(cache: ResourceByteCache) -> set[tuple[ResourceKind, CacheKey]]:
    return {
        (kind, key) for kind, items in cache._items.items() for key in OrderedDict.__iter__(items)
    }


def _assert_byte_accounting(cache: ResourceByteCache) -> None:
    resident = sum(len(value) for items in cache._items.values() for value in items.values())
    assert resident == sum(cache._bytes.values())
    assert resident == cache.stats().bytes


def _counting_cache(size: int) -> ResourceByteCache:
    cache = ResourceByteCache()
    cache._items[ResourceKind.OTHER] = CountingOrderedDict()
    for index in range(size):
        assert cache.put(f"OEBPS/resource-{index}.bin", index, ResourceKind.OTHER, b"")
    CountingOrderedDict.key_yields = 0
    return cache


def _provider(
    source_path: Path,
    cache: ResourceByteCache,
    revisions: Mapping[str, int],
) -> SnapshotResourceProvider:
    return SnapshotResourceProvider(
        source_path,
        1,
        dirty_overlay={},
        buffered={},
        deleted=frozenset(),
        files=frozenset(revisions),
        manifest_types={},
        revisions=revisions,
        sizes={},
        cache=cache,
    )


def test_invalidate_revisions_preserves_current_and_removes_old_revision() -> None:
    cache = ResourceByteCache()
    assert cache.put("chapter.xhtml", 1, ResourceKind.DOCUMENT, b"old")
    assert cache.put("chapter.xhtml", 2, ResourceKind.DOCUMENT, b"current")

    cache.invalidate_revisions({"chapter.xhtml": 2})

    assert _entries(cache) == {(ResourceKind.DOCUMENT, ("chapter.xhtml", 2))}


def test_invalidate_revisions_handles_multiple_paths_and_preserves_unrelated() -> None:
    cache = ResourceByteCache()
    assert cache.put("a.css", 1, ResourceKind.CSS, b"a-old")
    assert cache.put("a.css", 2, ResourceKind.CSS, b"a-new")
    assert cache.put("b.css", 3, ResourceKind.CSS, b"b-old")
    assert cache.put("b.css", 4, ResourceKind.CSS, b"b-new")
    assert cache.put("unrelated.css", 1, ResourceKind.CSS, b"untouched")
    assert cache.put("absent.css", 1, ResourceKind.CSS, b"also-untouched")

    cache.invalidate_revisions({"a.css": 2, "b.css": 4})

    assert _entries(cache) == {
        (ResourceKind.CSS, ("a.css", 2)),
        (ResourceKind.CSS, ("b.css", 4)),
        (ResourceKind.CSS, ("unrelated.css", 1)),
        (ResourceKind.CSS, ("absent.css", 1)),
    }


def test_invalidate_revisions_keeps_only_exact_revision_among_several() -> None:
    cache = ResourceByteCache()
    for revision in range(5):
        assert cache.put("image.png", revision, ResourceKind.IMAGE, bytes([revision]))

    cache.invalidate_revisions({"image.png": 3})
    cache.invalidate_revisions({"image.png": 3})

    assert _entries(cache) == {(ResourceKind.IMAGE, ("image.png", 3))}


def test_invalidate_revisions_removes_stale_revision_from_every_kind() -> None:
    cache = ResourceByteCache()
    for kind in (ResourceKind.DOCUMENT, ResourceKind.CSS, ResourceKind.OTHER):
        assert cache.put("shared", 1, kind, b"old")
        assert cache.put("shared", 2, kind, b"current")

    cache.invalidate_revisions({"shared": 2})

    assert _entries(cache) == {
        (ResourceKind.DOCUMENT, ("shared", 2)),
        (ResourceKind.CSS, ("shared", 2)),
        (ResourceKind.OTHER, ("shared", 2)),
    }


def test_invalidate_revisions_empty_inputs_are_no_op(tmp_path: Path) -> None:
    cache = ResourceByteCache()
    assert cache.put("untouched", 1, ResourceKind.OTHER, b"data")
    before = _entries(cache)

    cache.invalidate_revisions({})
    empty_cache = ResourceByteCache()
    empty_cache.invalidate_revisions({"missing": 1})
    _provider(tmp_path / "missing.epub", empty_cache, {})

    assert _entries(cache) == before
    assert empty_cache.stats().entries == 0


def test_byte_accounting_survives_batch_overwrite_eviction_and_clear() -> None:
    cache = ResourceByteCache(CacheLimits(documents=4, css=4, images=4, fonts=4, other=4))
    assert cache.put("a", 1, ResourceKind.OTHER, b"aa")
    assert cache.put("a", 2, ResourceKind.OTHER, b"bbb")
    assert cache.put("b", 1, ResourceKind.OTHER, b"c")
    _assert_byte_accounting(cache)

    cache.invalidate_revisions({"a": 2})
    _assert_byte_accounting(cache)
    assert cache.put("a", 2, ResourceKind.OTHER, b"dddd")
    _assert_byte_accounting(cache)
    assert cache.put("c", 1, ResourceKind.OTHER, b"z")
    _assert_byte_accounting(cache)

    cache.clear()
    _assert_byte_accounting(cache)
    assert cache.stats().entries == 0
    assert cache.stats().hits == cache.stats().misses == cache.stats().evictions == 0


def test_invalidate_revisions_scans_cache_once() -> None:
    cache_size = 1_000
    revision_paths = 100
    cache = _counting_cache(cache_size)

    cache.invalidate_revisions(
        {f"OEBPS/resource-{index}.bin": index for index in range(revision_paths)}
    )

    assert CountingOrderedDict.key_yields <= cache_size + len(ResourceKind)


def test_provider_construction_uses_single_cache_scan(tmp_path: Path) -> None:
    cache_size = 1_000
    revision_paths = 100
    cache = _counting_cache(cache_size)
    revisions = {f"OEBPS/resource-{index}.bin": index for index in range(revision_paths)}

    _provider(tmp_path / "missing.epub", cache, revisions)

    assert CountingOrderedDict.key_yields <= cache_size + len(ResourceKind)
