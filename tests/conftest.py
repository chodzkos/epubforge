"""Współdzielone fixtures testów."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

from epubforge.i18n import init_i18n

FIXTURE_EPUB = Path(__file__).parent / "fixtures" / "sample.epub"


@pytest.fixture(autouse=True)
def reset_i18n() -> None:
    """Każdy test startuje z polskim katalogiem źródłowym gettext."""
    init_i18n("pl")
    yield
    init_i18n("pl")


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
