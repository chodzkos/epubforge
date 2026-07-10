"""Współdzielone fixtures testów."""

from __future__ import annotations

import importlib.util
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pytest

from epubforge.i18n import init_i18n

FIXTURE_EPUB = Path(__file__).parent / "fixtures" / "sample.epub"
_MAKE_SAMPLE = Path(__file__).parent / "fixtures" / "make_sample_epub.py"


def _load_fixture_builder() -> Any:
    """Ładuje moduł generatora fixture'ów (nie jest pakietem importowalnym)."""
    spec = importlib.util.spec_from_file_location("make_sample_epub", _MAKE_SAMPLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def toc_epub(tmp_path: Path) -> Path:
    """EPUB do testów spisu treści (rozdziały z nagłówkami + nav z martwym wpisem)."""
    return Path(_load_fixture_builder().make_toc_epub(tmp_path / "toc.epub"))


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
def epub2_epub(tmp_path: Path) -> Path:
    """Zapisywalna kopia fixture EPUB 2 (do testów upgrade → EPUB 3)."""
    target = tmp_path / "book2.epub"
    shutil.copy2(Path(__file__).parent / "fixtures" / "sample_epub2.epub", target)
    return target


@pytest.fixture
def opf_bytes() -> bytes:
    """Surowa zawartość pliku OPF z fixture EPUB."""
    with zipfile.ZipFile(FIXTURE_EPUB) as zf:
        return zf.read("OEBPS/content.opf")
