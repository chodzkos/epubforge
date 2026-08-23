"""Regresje zapisu EPUB-a otwartego przez symlink."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import epubforge.core.epub as epub_module
from epubforge.core import Epub


def _symlink_or_skip(link: Path, target: Path) -> None:
    """Tworzy symlink względny albo pomija test na hoście bez wsparcia."""
    try:
        link.symlink_to(target.name)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"Symlinki niedostępne: {exc}")


def test_overwrite_through_symlink_updates_target_and_preserves_link(
    sample_epub: Path, tmp_path: Path
) -> None:
    """save() publikuje do ustalonego targetu, nie zastępuje symlinka."""
    target = tmp_path / "target.epub"
    target.write_bytes(sample_epub.read_bytes())
    link = tmp_path / "book-link.epub"
    _symlink_or_skip(link, target)

    with Epub(link) as epub:
        epub.write_file("OEBPS/symlink.txt", b"saved-through-link")
        assert epub.save() == link

    assert link.is_symlink()
    assert link.resolve() == target.resolve()
    assert target.with_name(target.name + ".bak").is_file()
    assert not link.with_name(link.name + ".bak").exists()
    with Epub(target) as reopened:
        assert reopened.read_file("OEBPS/symlink.txt") == b"saved-through-link"


def test_save_as_through_symlink_keeps_source_target_and_link(
    sample_epub: Path, tmp_path: Path
) -> None:
    """Save As czyta ustalony target, lecz publikuje wyłącznie nowy pathname."""
    target = tmp_path / "target.epub"
    target.write_bytes(sample_epub.read_bytes())
    original = target.read_bytes()
    link = tmp_path / "book-link.epub"
    output = tmp_path / "other.epub"
    _symlink_or_skip(link, target)

    with Epub(link) as epub:
        epub.write_file("OEBPS/save-as.txt", b"saved-as")
        assert epub.save(output) == output

    assert link.is_symlink()
    assert link.resolve() == target.resolve()
    assert target.read_bytes() == original
    assert not target.with_name(target.name + ".bak").exists()
    with Epub(output) as reopened:
        assert reopened.read_file("OEBPS/save-as.txt") == b"saved-as"


def test_retargeted_symlink_session_remains_bound_to_original_target(
    sample_epub: Path, tmp_path: Path
) -> None:
    """Retarget linku po open nie przełącza aktywnej sesji na drugi EPUB."""
    target_a = tmp_path / "target-a.epub"
    target_b = tmp_path / "target-b.epub"
    target_a.write_bytes(sample_epub.read_bytes())
    target_b.write_bytes(sample_epub.read_bytes())
    link = tmp_path / "book-link.epub"
    _symlink_or_skip(link, target_a)

    with Epub(link) as epub:
        epub.write_file("OEBPS/bound.txt", b"target-a")
        link.unlink()
        _symlink_or_skip(link, target_b)
        assert epub.save() == link
        assert epub.read_file("OEBPS/bound.txt") == b"target-a"

    assert link.is_symlink()
    assert link.resolve() == target_b.resolve()
    with Epub(target_a) as reopened_a:
        assert reopened_a.read_file("OEBPS/bound.txt") == b"target-a"
    with Epub(target_b) as reopened_b, pytest.raises(KeyError):
        reopened_b.read_file("OEBPS/bound.txt")


def test_symlink_source_rejects_original_target_path_replacement(
    sample_epub: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Identity nadal odrzuca podmianę pathname targetu ustalonego przy open."""
    target = tmp_path / "target.epub"
    target.write_bytes(sample_epub.read_bytes())
    link = tmp_path / "book-link.epub"
    _symlink_or_skip(link, target)
    real_stat = os.stat
    canonical_target = target.resolve()

    with Epub(link) as epub:
        epub.write_file("OEBPS/pending.txt", b"pending")
        target_stat = real_stat(target, follow_symlinks=False)
        changed_stat = SimpleNamespace(
            st_dev=target_stat.st_dev,
            st_ino=target_stat.st_ino,
            st_size=target_stat.st_size + 1,
            st_mtime_ns=target_stat.st_mtime_ns,
            st_ctime_ns=target_stat.st_ctime_ns,
        )

        def stat_with_changed_target(path: object, **kwargs: object) -> os.stat_result:
            if path == canonical_target:
                return changed_stat  # type: ignore[return-value]
            return real_stat(path, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(epub_module.os, "stat", stat_with_changed_target)
        with pytest.raises(OSError, match="zmienił się od czasu otwarcia"):
            epub.save()
        assert epub.pending_changes().modified["OEBPS/pending.txt"] == b"pending"
