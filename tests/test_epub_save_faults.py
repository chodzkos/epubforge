"""Testy fault-injection bezpiecznego zapisu ``Epub.save`` (``core/epub.py``, F-14).

Kryterium: oryginał NIGDY nie zostaje uszkodzony — niezależnie od tego, czy zapis
padnie na braku miejsca (ENOSPC), braku uprawnień (PermissionError) czy na
przerwanej podmianie (``os.replace``). Sprawdzamy też, że po błędzie nie zostaje
żaden plik tymczasowy, obsługę ``output_path == source`` oraz rotację backupów.
"""

from __future__ import annotations

import errno
import zipfile
from pathlib import Path

import pytest

from epubforge.core._epub_write import numbered_backup, rotate_backups
from epubforge.core.epub import Epub


def _leftover_tmps(directory: Path) -> list[Path]:
    """Zwraca ewentualne pliki tymczasowe zapisu pozostałe w katalogu."""
    return [p for p in directory.iterdir() if p.name.endswith(".tmp")]


def test_enospc_during_write_leaves_original_intact(
    sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Brak miejsca w trakcie zapisu ZIP → oryginał nietknięty, brak tempa."""
    original = sample_epub.read_bytes()

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    with Epub(sample_epub) as epub:
        epub.write_file("OEBPS/content.opf", b"<xml/>")
        # write_epub tworzy temp, po czym woła _write_zip_entries — wstrzykujemy tam ENOSPC.
        monkeypatch.setattr("epubforge.core._epub_write._write_zip_entries", boom)
        with pytest.raises(OSError, match="No space"):
            epub.save()

    assert sample_epub.read_bytes() == original  # oryginał bez zmian
    assert _leftover_tmps(sample_epub.parent) == []  # temp posprzątany


def test_permission_error_on_replace_leaves_original_intact(
    sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PermissionError przy ``os.replace`` → oryginał nietknięty, brak tempa."""
    original = sample_epub.read_bytes()

    def deny(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("Access is denied")

    with Epub(sample_epub) as epub:
        epub.write_file("OEBPS/content.opf", b"<xml/>")
        monkeypatch.setattr("epubforge.core._epub_write.os.replace", deny)
        with pytest.raises(PermissionError):
            epub.save()

    assert sample_epub.read_bytes() == original
    assert _leftover_tmps(sample_epub.parent) == []


def test_interrupted_replace_leaves_original_intact(
    sample_epub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Przerwana podmiana (``os.replace`` rzuca) → oryginał czytelny i niezmieniony."""
    original = sample_epub.read_bytes()

    def interrupted(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.EIO, "I/O error during rename")

    with Epub(sample_epub) as epub:
        epub.write_file("OEBPS/content.opf", b"<xml/>")
        monkeypatch.setattr("epubforge.core._epub_write.os.replace", interrupted)
        with pytest.raises(OSError, match="I/O error"):
            epub.save()

    # Oryginał wciąż jest poprawnym, otwieralnym archiwum o niezmienionej treści.
    assert sample_epub.read_bytes() == original
    with zipfile.ZipFile(sample_epub) as zf:
        assert zf.testzip() is None
    assert _leftover_tmps(sample_epub.parent) == []


def test_backup_created_before_overwrite(sample_epub: Path) -> None:
    """Nadpisanie oryginału robi backup ``.bak`` o treści sprzed zapisu."""
    before = sample_epub.read_bytes()
    with Epub(sample_epub) as epub:
        epub.write_file("OEBPS/content.opf", b"<xml/>")
        epub.save()
    backup = sample_epub.with_name(sample_epub.name + ".bak")
    assert backup.is_file()
    assert backup.read_bytes() == before  # backup = stan sprzed nadpisania


def test_output_path_equal_to_source_is_overwrite(sample_epub: Path) -> None:
    """``save(output_path == source)`` działa jak nadpisanie: backup + trwałe zmiany."""
    with Epub(sample_epub) as epub:
        epub.write_file("OEBPS/new.txt", b"dodane")
        result = epub.save(output_path=sample_epub)
        assert result == sample_epub
    # Backup powstał (ścieżka == źródło jest traktowana jak nadpisanie oryginału).
    assert sample_epub.with_name(sample_epub.name + ".bak").is_file()
    # Zmiana faktycznie utrwalona w oryginale.
    with zipfile.ZipFile(sample_epub) as zf:
        assert zf.read("OEBPS/new.txt") == b"dodane"


def test_save_beside_keeps_original_and_session(sample_epub: Path, tmp_path: Path) -> None:
    """``save(inna_ścieżka)`` pisze kopię, nie robi backupu i zostawia oryginał."""
    original = sample_epub.read_bytes()
    out = tmp_path / "kopia.epub"
    with Epub(sample_epub) as epub:
        epub.write_file("OEBPS/new.txt", b"x")
        assert epub.save(output_path=out) == out
        # Sesja wciąż otwarta na oryginale — kolejny odczyt działa.
        assert epub.read_file("OEBPS/content.opf")
    assert sample_epub.read_bytes() == original  # oryginał bez zmian ani backupu
    assert not sample_epub.with_name(sample_epub.name + ".bak").exists()
    assert out.is_file()


def test_backup_rotation_keeps_retention(sample_epub: Path) -> None:
    """Kolejne backupy rotują: najnowszy pod ``.bak``, starsze numerowane, prune do retencji."""
    primary = sample_epub.with_name(sample_epub.name + ".bak")
    # Trzy kolejne nadpisania z retencją 3 → .bak, .bak.1, .bak.2; brak .bak.3.
    for index in range(3):
        with Epub(sample_epub) as epub:
            epub.write_file("OEBPS/content.opf", f"<xml v='{index}'/>".encode())
            epub.save(backup_retention=3)
    assert primary.is_file()
    assert numbered_backup(primary, 1).is_file()
    assert numbered_backup(primary, 2).is_file()
    assert not numbered_backup(primary, 3).exists()  # najstarszy odcięty przez retencję


def test_rotate_backups_retention_one_no_rotation(tmp_path: Path) -> None:
    """``retention <= 1`` = brak rotacji (kopia nadpisuje jedyny ``.bak``)."""
    primary = tmp_path / "book.epub.bak"
    primary.write_text("stary")
    rotate_backups(primary, retention=1)
    assert not numbered_backup(primary, 1).exists()  # nic nie zrotowano
    assert primary.read_text() == "stary"  # nietknięty (nadpisze go dopiero copy2)
