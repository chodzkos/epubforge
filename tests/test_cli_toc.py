"""Testy CLI ``epubforge toc`` — show / generate / repair (na fixture toc_epub)."""

from __future__ import annotations

from pathlib import Path

import pytest

from epubforge.cli.main import main


def test_toc_show(capsys: pytest.CaptureFixture[str], toc_epub: Path) -> None:
    """--show wypisuje bieżący spis z istniejącego nav (z martwym wpisem)."""
    assert main(["toc", str(toc_epub), "--show"]) == 0
    out = capsys.readouterr().out
    assert "Rozdział pierwszy" in out
    assert "Martwy wpis" in out


def test_toc_generate(capsys: pytest.CaptureFixture[str], toc_epub: Path) -> None:
    """--generate buduje spis z nagłówków i zapisuje plik."""
    assert main(["toc", str(toc_epub), "--generate", "--max-level", "3"]) == 0
    out = capsys.readouterr().out
    assert "Wstęp do tematu" in out
    assert "Zapisano" in out


def test_toc_repair_dry_run(capsys: pytest.CaptureFixture[str], toc_epub: Path) -> None:
    """--repair --dry-run pokazuje martwe wpisy i nie zapisuje zmian."""
    assert main(["toc", str(toc_epub), "--repair", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "missing.xhtml" in out
    assert "dry-run" in out.lower()


def test_toc_repair_writes(capsys: pytest.CaptureFixture[str], toc_epub: Path) -> None:
    """--repair usuwa martwy wpis i zapisuje (kod 0, komunikat o liczbie)."""
    assert main(["toc", str(toc_epub), "--repair"]) == 0
    out = capsys.readouterr().out
    assert "Usunięto" in out
