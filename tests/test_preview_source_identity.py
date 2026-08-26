"""Regresje tożsamości źródła podglądu (EF-020 CHECK/USE)."""

from __future__ import annotations

import os
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from epubforge.core import Epub, PendingChanges
from epubforge.gui.preview import resources as resources_module
from epubforge.gui.preview.backend import DiagnosticCategory
from epubforge.gui.preview.cache import ResourceByteCache
from epubforge.gui.preview.controller import PreviewController
from epubforge.gui.preview.resources import SnapshotResourceProvider
from epubforge.gui.preview.session import PreviewSession

_CHAPTER = "OEBPS/text/chapter1.xhtml"
_NAV = "OEBPS/nav.xhtml"
_MARKER_B = b"REPLACED-SOURCE-B"


def _marker_epub(source: Path, target: Path, marker: bytes) -> Path:
    """Kopiuje EPUB i wstawia znacznik na początek rozdziału."""
    with zipfile.ZipFile(source) as incoming, zipfile.ZipFile(target, "w") as outgoing:
        for info in incoming.infolist():
            data = incoming.read(info.filename)
            if info.filename == _CHAPTER:
                data = marker + data
            outgoing.writestr(info, data)
    return target


def _provider(path: Path) -> SnapshotResourceProvider:
    """Buduje provider bez preloadu, żeby odczyt źródła szedł przez CHECK/USE."""
    return SnapshotResourceProvider(
        path,
        1,
        dirty_overlay={},
        buffered={},
        deleted=frozenset(),
        files=frozenset({_CHAPTER, _NAV}),
        manifest_types={},
        revisions={_CHAPTER: 1, _NAV: 1},
        sizes={_CHAPTER: 64, _NAV: 64},
        cache=ResourceByteCache(),
        source_signature=resources_module._source_signature(path),
    )


def test_unchanged_source_still_reads_original_chapter(sample_epub: Path) -> None:
    """Niezmienione źródło nadal oddaje oryginalny wpis."""
    original = zipfile.ZipFile(sample_epub).read(_CHAPTER)
    provider = _provider(sample_epub)

    assert provider.read(_CHAPTER, 1) == original


def test_atomic_replace_between_stat_check_and_path_open_does_not_return_b(
    tmp_path: Path, sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Po CHECK nie wolno cicho oddać EPUB-a podmienionego przed USE."""
    source = tmp_path / "preview-source.epub"
    replacement = tmp_path / "preview-b.epub"
    source.write_bytes(sample_epub.read_bytes())
    _marker_epub(sample_epub, replacement, _MARKER_B)
    original = zipfile.ZipFile(source).read(_CHAPTER)
    provider = _provider(source)
    original_open: Callable[..., Any] = Path.open

    def racing_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        handle = original_open(self, *args, **kwargs)
        if self == source:
            os.replace(replacement, source)
        return handle

    monkeypatch.setattr(Path, "open", racing_open)
    data = provider.read(_CHAPTER, 1)

    assert data != _MARKER_B + original
    assert data is None or data == original
    assert data is None or _MARKER_B not in data


def test_same_expected_identity_is_accepted(sample_epub: Path) -> None:
    """Ten sam plik, ten sam fingerprint — odczyt źródła pozostaje dozwolony."""
    provider = _provider(sample_epub)

    assert provider.read(_CHAPTER, 1) is not None
    assert provider.read(_NAV, 1) is not None


def test_identity_mismatch_after_generation_rejects_source_read(
    tmp_path: Path, sample_epub: Path
) -> None:
    """Gdy pathname wskazuje inny obiekt po snapshotcie, provider nie czyta B."""
    source = tmp_path / "preview-source.epub"
    replacement = tmp_path / "preview-b.epub"
    source.write_bytes(sample_epub.read_bytes())
    _marker_epub(sample_epub, replacement, _MARKER_B)
    epub = Epub(source)
    epub.open()
    session = PreviewSession.create(epub, source)
    generation = session.advance(epub, _CHAPTER, {})
    original_nav = zipfile.ZipFile(source).read(_NAV)
    session.clear_cache()
    os.replace(replacement, source)

    data = generation.resource_provider.read(_NAV, generation.generation_id)

    assert data is None
    assert zipfile.ZipFile(source).read(_CHAPTER).startswith(_MARKER_B)
    assert original_nav
    epub.close()


def test_pending_overlay_survives_source_identity_mismatch(
    tmp_path: Path, sample_epub: Path
) -> None:
    """Dirty/pending wygrywają ze źródłem i nie znikają przy mismatchu identity."""
    source = tmp_path / "preview-source.epub"
    replacement = tmp_path / "preview-b.epub"
    source.write_bytes(sample_epub.read_bytes())
    _marker_epub(sample_epub, replacement, _MARKER_B)
    epub = Epub(source)
    epub.open()
    pending = PendingChanges({_NAV: b"pending-nav"}, frozenset())
    session = PreviewSession.create(epub, source)
    generation = session.advance(
        epub,
        _CHAPTER,
        {_CHAPTER: b"dirty-chapter"},
        pending=pending,
    )
    os.replace(replacement, source)
    provider = generation.resource_provider

    assert provider.read(_CHAPTER, generation.generation_id) == b"dirty-chapter"
    assert provider.read(_NAV, generation.generation_id) == b"pending-nav"
    assert provider.read("OEBPS/styles/main.css", generation.generation_id) is None
    epub.close()


def test_source_unchanged_with_pending_still_previews(sample_epub: Path) -> None:
    """Niezmienione źródło + pending overlay nadal składa spójny podgląd."""
    epub = Epub(sample_epub)
    epub.open()
    pending = PendingChanges({_NAV: b"pending-nav"}, frozenset())
    session = PreviewSession.create(epub, sample_epub)
    generation = session.advance(epub, _CHAPTER, {}, pending=pending)
    original_chapter = epub.read_source_file_limited(_CHAPTER, 1_000_000)

    assert generation.resource_provider.read(_CHAPTER, generation.generation_id) == original_chapter
    assert generation.resource_provider.read(_NAV, generation.generation_id) == b"pending-nav"
    epub.close()


def test_same_size_same_mtime_fingerprint_collision_is_identity_residual(
    tmp_path: Path,
) -> None:
    """Fingerprint (dev, ino, size, mtime) nie rozróżnia rewrite w tym samym inode."""
    source = tmp_path / "collision-a.epub"
    replacement = tmp_path / "collision-b.epub"
    with zipfile.ZipFile(source, "w") as archive:
        info = zipfile.ZipInfo(_CHAPTER, date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, b"A" * 32)
    with zipfile.ZipFile(replacement, "w") as archive:
        info = zipfile.ZipInfo(_CHAPTER, date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, b"B" * 32)
    assert source.stat().st_size == replacement.stat().st_size
    provider = _provider(source)
    expected = resources_module._source_signature(source)
    original_stat = source.stat()
    with source.open("r+b") as handle:
        handle.write(replacement.read_bytes())
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())
    os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    assert resources_module._source_signature(source) == expected
    data = provider.read(_CHAPTER, 1)
    assert data in {None, b"A" * 32, b"B" * 32}


def test_symlink_retarget_does_not_return_replacement(
    tmp_path: Path, sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Podmiana celu symlinku po CHECK nie może dostarczyć EPUB-a B."""
    target_a = tmp_path / "a.epub"
    target_b = tmp_path / "b.epub"
    link = tmp_path / "book-link.epub"
    next_link = tmp_path / "book-next.epub"
    target_a.write_bytes(sample_epub.read_bytes())
    _marker_epub(sample_epub, target_b, _MARKER_B)
    try:
        link.symlink_to(target_a)
    except OSError:
        pytest.skip("system nie pozwala utworzyć symlinku")
    original = zipfile.ZipFile(link).read(_CHAPTER)
    provider = _provider(link)
    original_open: Callable[..., Any] = Path.open

    def racing_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        handle = original_open(self, *args, **kwargs)
        if self == link:
            next_link.symlink_to(target_b)
            os.replace(next_link, link)
        return handle

    monkeypatch.setattr(Path, "open", racing_open)
    data = provider.read(_CHAPTER, 1)

    assert data != _MARKER_B + original
    assert data is None or _MARKER_B not in data


def test_controller_rejects_source_replaced_before_snapshot(
    tmp_path: Path, sample_epub: Path
) -> None:
    """Otwarta sesja Epub A i podmienione path B dają kontrolowane odrzucenie."""
    source = tmp_path / "preview-source.epub"
    replacement = tmp_path / "preview-b.epub"
    source.write_bytes(sample_epub.read_bytes())
    _marker_epub(sample_epub, replacement, _MARKER_B)
    epub = Epub(source)
    epub.open()
    session = PreviewSession.create(epub, source)
    os.replace(replacement, source)

    result = PreviewController().build(
        epub=epub,
        session=session,
        current_path=_CHAPTER,
        current_text='<html xmlns="http://www.w3.org/1999/xhtml"><body>NOWY</body></html>',
        dirty={},
        media_types={_CHAPTER: "application/xhtml+xml"},
    )

    assert result.snapshot is None
    assert result.diagnostic is not None
    assert result.diagnostic.category is DiagnosticCategory.PREVIEW_LIMIT
    assert result.diagnostic.problem_kind == "zrodlo_zmienione"
    assert "źródłowy" in result.diagnostic.message.lower()
    epub.close()
