"""Testy batchowego CLI i dry-run diffów."""

from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path

import pytest

from epubforge.cli.main import main

_FIXTURE = Path(__file__).parent / "fixtures" / "sample.epub"
_PRESET_PATH = "OEBPS/styles/epubforge-preset.css"


def _copy_fixture(tmp_path: Path, name: str) -> Path:
    """Kopiuje fixture EPUB pod wybraną nazwę."""
    target = tmp_path / name
    shutil.copy2(_FIXTURE, target)
    return target


def _sha256(path: Path) -> str:
    """Zwraca hash SHA-256 pliku."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contains_preset(path: Path) -> bool:
    """Czy EPUB zawiera arkusz presetu dopięty przez fix --preset."""
    with zipfile.ZipFile(path) as zf:
        return _PRESET_PATH in zf.namelist()


def test_batch_fix_happy_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """fix obsługuje wiele plików i raportuje tabelą."""
    first = _copy_fixture(tmp_path, "a.epub")
    second = _copy_fixture(tmp_path, "b.epub")

    exit_code = main(["fix", str(first), str(second), "--preset", "reader-friendly", "--jobs", "2"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "OK" in out
    assert str(first) in out
    assert str(second) in out
    assert _contains_preset(first)
    assert _contains_preset(second)


def test_batch_failure_keeps_processing_other_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Uszkodzony plik daje exit 1, ale pozostałe EPUB-y są przetwarzane."""
    first = _copy_fixture(tmp_path, "a.epub")
    broken = tmp_path / "broken.epub"
    broken.write_bytes(b"not a zip")
    second = _copy_fixture(tmp_path, "b.epub")

    exit_code = main(
        [
            "fix",
            str(first),
            str(broken),
            str(second),
            "--preset",
            "reader-friendly",
            "--jobs",
            "2",
        ]
    )

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "FAIL" in out
    assert str(broken) in out
    assert _contains_preset(first)
    assert _contains_preset(second)


def test_dry_run_does_not_change_file_bytes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--dry-run pokazuje diff, ale nie zmienia żadnego bajtu na dysku."""
    book = _copy_fixture(tmp_path, "book.epub")
    before = _sha256(book)

    exit_code = main(["hyphenate", str(book), "--method", "css", "--dry-run"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert before == _sha256(book)
    assert "--- a/OEBPS/text/chapter1.xhtml" in out
    assert "nic nie zapisano" in out
