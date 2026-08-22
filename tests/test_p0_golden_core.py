"""P0 regressions for writer/opener symmetry and transactional saves."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

from epubforge.core._archive import ArchiveLimits, validate_archive
from epubforge.core._epub_write import publish_staged, stage_epub, write_epub
from epubforge.core.epub import Epub
from epubforge.core.exceptions import OpfNotFoundError, ResourceLimitError

pytestmark = pytest.mark.security

_UNSAFE_NAMES = (
    "",
    "../escape.xhtml",
    "OEBPS/../../escape.xhtml",
    "/absolute.xhtml",
    "C:/windows.xhtml",
    "OEBPS\\windows.xhtml",
    "bad\x00name.xhtml",
    "OEBPS/./chapter.xhtml",
    "OEBPS//chapter.xhtml",
)


@pytest.mark.parametrize("name", _UNSAFE_NAMES)
def test_public_writer_rejects_noncanonical_name_before_pending_changes(
    sample_epub: Path, name: str
) -> None:
    with Epub(sample_epub) as epub:
        before = epub.pending_changes()
        with pytest.raises(ResourceLimitError):
            epub.write_file(name, b"synthetic")
        assert epub.pending_changes() == before


@pytest.mark.parametrize("name", _UNSAFE_NAMES)
def test_low_level_writer_rejects_noncanonical_name_without_publication(
    sample_epub: Path, tmp_path: Path, name: str
) -> None:
    target = tmp_path / "target.epub"
    target.write_bytes(b"target-sentinel")
    with pytest.raises(ResourceLimitError):
        write_epub(sample_epub, target, {name: b"synthetic"}, set())
    assert target.read_bytes() == b"target-sentinel"


@pytest.mark.parametrize("name", _UNSAFE_NAMES)
def test_delete_rejects_noncanonical_name_before_pending_changes(
    sample_epub: Path, name: str
) -> None:
    with Epub(sample_epub) as epub:
        before = epub.pending_changes()
        with pytest.raises(ResourceLimitError):
            epub.delete_file(name)
        assert epub.pending_changes() == before


def test_low_level_writer_validates_deleted_names(sample_epub: Path, tmp_path: Path) -> None:
    target = tmp_path / "target.epub"
    with pytest.raises(ResourceLimitError):
        write_epub(sample_epub, target, {}, {"OEBPS//invalid.xhtml"})
    assert not target.exists()


def test_valid_names_round_trip_through_normal_opener(sample_epub: Path, tmp_path: Path) -> None:
    target = tmp_path / "valid.epub"
    additions = {
        "OEBPS/text/chapter-2.xhtml": b"<html/>",
        "OEBPS/images/zażółć.png": b"synthetic-image",
        "OEBPS/empty-dir/": b"",
    }
    with Epub(sample_epub) as epub:
        for name, data in additions.items():
            epub.write_file(name, data)
        epub.save(target)
    with Epub(target) as reopened:
        for name, data in additions.items():
            assert reopened.read_file(name) == data


@pytest.mark.parametrize("overwrite", [False, True], ids=["save-as", "overwrite"])
def test_highly_compressible_application_data_saves_and_reopens(
    sample_epub: Path, tmp_path: Path, overwrite: bool
) -> None:
    limits = ArchiveLimits(max_compression_ratio=10.0, ratio_check_min_size=128)
    payload = b"A" * 4096
    original = sample_epub.read_bytes()
    target = sample_epub if overwrite else tmp_path / "save-as.epub"
    with Epub(sample_epub, limits=limits) as epub:
        epub.write_file("OEBPS/text/compressible.xhtml", payload)
        epub.save(None if overwrite else target)
        if not overwrite:
            assert epub.pending_changes().modified["OEBPS/text/compressible.xhtml"] == payload
    if not overwrite:
        assert sample_epub.read_bytes() == original
    with Epub(target, limits=limits) as reopened:
        assert reopened.read_file("OEBPS/text/compressible.xhtml") == payload
    with zipfile.ZipFile(target) as zf:
        validate_archive(zf, limits)
        info = zf.getinfo("OEBPS/text/compressible.xhtml")
        assert info.compress_type == zipfile.ZIP_STORED


@pytest.mark.parametrize("file_size", [1, 4096])
def test_nonempty_entry_with_zero_compressed_size_is_rejected(file_size: int) -> None:
    class FakeZip:
        def infolist(self) -> list[zipfile.ZipInfo]:
            info = zipfile.ZipInfo("OEBPS/impossible.bin")
            info.file_size = file_size
            info.compress_size = 0
            return [info]

    with pytest.raises(ResourceLimitError, match="skompresowany"):
        validate_archive(FakeZip(), ArchiveLimits(ratio_check_min_size=128))  # type: ignore[arg-type]


@pytest.mark.parametrize("overwrite", [False, True], ids=["save-as", "overwrite"])
def test_missing_container_candidate_is_rejected_before_publication_or_backup(
    sample_epub: Path, tmp_path: Path, overwrite: bool
) -> None:
    target = sample_epub if overwrite else tmp_path / "save-as.epub"
    if not overwrite:
        target.write_bytes(b"target-sentinel")
    before = target.read_bytes()
    backup = sample_epub.with_name(sample_epub.name + ".bak")
    with Epub(sample_epub) as epub:
        epub.delete_file("META-INF/container.xml")
        pending = epub.pending_changes()
        with pytest.raises(OpfNotFoundError):
            epub.save(None if overwrite else target)
        assert epub.pending_changes() == pending
        assert epub.read_file("OEBPS/content.opf")
    assert target.read_bytes() == before
    assert not backup.exists()


def test_stage_failure_preserves_original_pending_and_open_session(
    sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = sample_epub.read_bytes()
    with Epub(sample_epub) as epub:
        epub.write_file("OEBPS/new.xhtml", b"pending")
        epub.delete_file("OEBPS/nav.xhtml")
        pending = epub.pending_changes()

        def fail(*_args: object, **_kwargs: object) -> None:
            raise OSError("synthetic stage failure")

        monkeypatch.setattr("epubforge.core._epub_write._write_zip_entries", fail)
        with pytest.raises(OSError, match="stage failure"):
            epub.save()
        assert epub.pending_changes() == pending
        assert epub.read_file("OEBPS/new.xhtml") == b"pending"
        assert "OEBPS/nav.xhtml" not in epub.list_files()
    assert sample_epub.read_bytes() == original
    assert not sample_epub.with_name(sample_epub.name + ".bak").exists()


def test_save_as_stage_failure_preserves_existing_target_and_pending(
    sample_epub: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = sample_epub.read_bytes()
    target = tmp_path / "save-as.epub"
    target.write_bytes(b"target-sentinel")
    with Epub(sample_epub) as epub:
        epub.write_file("OEBPS/new.xhtml", b"pending")
        pending = epub.pending_changes()

        def fail(*_args: object, **_kwargs: object) -> None:
            raise OSError("synthetic save-as stage failure")

        monkeypatch.setattr("epubforge.core._epub_write._write_zip_entries", fail)
        with pytest.raises(OSError, match="save-as stage failure"):
            epub.save(target)
        assert epub.pending_changes() == pending
        assert epub.read_file("OEBPS/new.xhtml") == b"pending"
    assert sample_epub.read_bytes() == original
    assert target.read_bytes() == b"target-sentinel"


def test_backup_failure_preserves_original_pending_and_open_session(
    sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = sample_epub.read_bytes()
    with Epub(sample_epub) as epub:
        epub.write_file("OEBPS/new.xhtml", b"pending")
        pending = epub.pending_changes()

        def fail(*, retention: int) -> Path:
            del retention
            raise OSError("synthetic backup failure")

        monkeypatch.setattr(epub, "backup", fail)
        with pytest.raises(OSError, match="backup failure"):
            epub.save()
        assert epub.pending_changes() == pending
        assert epub.read_file("OEBPS/new.xhtml") == b"pending"
    assert sample_epub.read_bytes() == original


def test_publish_failure_preserves_original_pending_and_open_session(
    sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = sample_epub.read_bytes()
    with Epub(sample_epub) as epub:
        epub.write_file("OEBPS/new.xhtml", b"pending")
        pending = epub.pending_changes()

        def fail(*_args: object, **_kwargs: object) -> None:
            raise PermissionError("synthetic publish failure")

        monkeypatch.setattr("epubforge.core._epub_write.os.replace", fail)
        with pytest.raises(PermissionError, match="publish failure"):
            epub.save()
        assert epub.pending_changes() == pending
        assert epub.read_file("OEBPS/new.xhtml") == b"pending"
    assert sample_epub.read_bytes() == original


def test_transient_reopen_failure_preserves_pending_and_recovers_session(
    sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    epub = Epub(sample_epub)
    epub.open()
    epub.write_file("OEBPS/new.xhtml", b"pending")
    pending = epub.pending_changes()
    real_open = epub.open
    calls = 0

    def fail_once() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("synthetic reopen failure")
        real_open()

    monkeypatch.setattr(epub, "open", fail_once)
    try:
        with pytest.raises(OSError, match="reopen failure"):
            epub.save()
        assert epub.pending_changes() == pending
        assert epub.read_file("OEBPS/new.xhtml") == b"pending"
        with Epub(sample_epub) as reopened:
            assert reopened.read_file("OEBPS/new.xhtml") == b"pending"
    finally:
        epub.close()


def test_source_handle_is_closed_before_publish_for_windows_compatibility(
    sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import epubforge.core.epub as epub_module

    real_publish = epub_module.publish_staged
    with Epub(sample_epub) as epub:
        epub.write_file("OEBPS/new.xhtml", b"pending")

        def checked_publish(staged: object, target: Path) -> None:
            assert epub._zip is None
            real_publish(staged, target)  # type: ignore[arg-type]

        monkeypatch.setattr(epub_module, "publish_staged", checked_publish)
        epub.save()
        assert epub.read_file("OEBPS/new.xhtml") == b"pending"


def test_save_rejects_source_path_replaced_after_session_open(
    sample_epub: Path, tmp_path: Path
) -> None:
    original = sample_epub.read_bytes()
    replacement = tmp_path / "replacement.epub"
    shutil.copy2(sample_epub, replacement)
    with zipfile.ZipFile(replacement, "a") as archive:
        archive.writestr("OEBPS/replacement.txt", b"replacement")
    epub = Epub(sample_epub)
    epub.open()
    epub.write_file("OEBPS/pending.txt", b"pending")
    replacement.replace(sample_epub)
    try:
        with pytest.raises(OSError, match="zmienił się od czasu otwarcia"):
            epub.save()
        assert epub.pending_changes().modified["OEBPS/pending.txt"] == b"pending"
        assert sample_epub.read_bytes() != original
        assert not sample_epub.with_name(sample_epub.name + ".bak").exists()
    finally:
        epub.close()


def test_cleanup_failure_does_not_mask_publish_failure(
    sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Epub(sample_epub) as epub:
        epub.write_file("OEBPS/new.xhtml", b"pending")

        def fail_publish(*_args: object, **_kwargs: object) -> None:
            raise PermissionError("publish root cause")

        def fail_cleanup(*_args: object, **_kwargs: object) -> None:
            raise OSError("cleanup must not mask")

        monkeypatch.setattr("epubforge.core.epub.publish_staged", fail_publish)
        monkeypatch.setattr("epubforge.core.epub.discard_staged", fail_cleanup)
        with pytest.raises(PermissionError, match="publish root cause"):
            epub.save()


def test_backup_copy_failure_keeps_existing_history_unchanged(
    sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = sample_epub.with_name(sample_epub.name + ".bak")
    older = primary.with_name(primary.name + ".1")
    primary.write_bytes(b"latest-backup")
    older.write_bytes(b"older-backup")
    with Epub(sample_epub) as epub:
        epub.write_file("OEBPS/new.xhtml", b"pending")

        def fail_copy(*_args: object, **_kwargs: object) -> None:
            raise OSError("backup copy failure")

        monkeypatch.setattr("epubforge.core.epub.shutil.copyfileobj", fail_copy)
        with pytest.raises(OSError, match="backup copy failure"):
            epub.save(backup_retention=2)
        assert epub.read_file("OEBPS/new.xhtml") == b"pending"
    assert primary.read_bytes() == b"latest-backup"
    assert older.read_bytes() == b"older-backup"


def test_candidate_changed_after_validation_is_not_published(
    sample_epub: Path, tmp_path: Path
) -> None:
    target = tmp_path / "target.epub"
    target.write_bytes(b"target-sentinel")
    staged = stage_epub(sample_epub, target, {}, set())
    staged.path.write_bytes(b"changed-after-validation")
    try:
        with pytest.raises(OSError, match="zmienił się po walidacji"):
            publish_staged(staged, target)
        assert target.read_bytes() == b"target-sentinel"
    finally:
        staged.path.unlink(missing_ok=True)


def test_recovery_failure_keeps_original_exception_and_explicit_pending_state(
    sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    epub = Epub(sample_epub)
    epub.open()
    epub.write_file("OEBPS/new.xhtml", b"pending")
    pending = epub.pending_changes()
    calls = 0

    def fail_differently() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("primary reopen failure")
        raise RuntimeError("recovery failure must not escape")

    monkeypatch.setattr(epub, "open", fail_differently)
    try:
        with pytest.raises(OSError, match="primary reopen failure"):
            epub.save()
        assert epub._zip is None
        assert epub.pending_changes() == pending
        with Epub(sample_epub) as reopened:
            assert reopened.read_file("OEBPS/new.xhtml") == b"pending"
    finally:
        epub.close()
