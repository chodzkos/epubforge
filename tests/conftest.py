"""Współdzielone fixtures testów."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

FIXTURE_EPUB = Path(__file__).parent / "fixtures" / "sample.epub"


@pytest.fixture
def sample_epub(tmp_path: Path) -> Path:
    """Zapisywalna kopia fixture EPUB w katalogu tymczasowym."""
    target = tmp_path / "book.epub"
    shutil.copy2(FIXTURE_EPUB, target)
    return target


@pytest.fixture
def opf_bytes() -> bytes:
    """Surowa zawartość pliku OPF z fixture EPUB."""
    with zipfile.ZipFile(FIXTURE_EPUB) as zf:
        return zf.read("OEBPS/content.opf")
