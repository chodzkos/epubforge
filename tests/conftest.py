"""Współdzielone fixtures testów."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

from epubforge.i18n import init_i18n

FIXTURE_EPUB = Path(__file__).parent / "fixtures" / "sample.epub"


@pytest.fixture(autouse=True)
def reset_i18n(monkeypatch: pytest.MonkeyPatch) -> None:
    """Każdy test startuje z polskim katalogiem źródłowym gettext.

    CLI czyta język z configu, a przy `auto` zależy od języka systemu runnera
    (macOS/Windows na GitHub Actions zwykle dają English). Testy starszych
    komend zakładają polskie komunikaty, więc stabilizujemy config CLI w testach.
    Dedykowane testy i18n nadal mogą nadpisać ten mock lokalnie.
    """
    monkeypatch.setattr("epubforge.cli.main.load_config", lambda _path: {"language": "pl"})
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
