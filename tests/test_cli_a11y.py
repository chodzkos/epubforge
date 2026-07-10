"""Testy CLI ``epubforge a11y`` — kody wyjścia (mock detekcji i run_ace)."""

from __future__ import annotations

from pathlib import Path

import pytest

from epubforge.cli import a11y
from epubforge.cli.main import main
from epubforge.core import Tool
from epubforge.validators import AceMessage, AceReport, Severity


def _tools(*, ready: bool) -> dict[str, Tool]:
    """Zwraca mapę narzędzi z dostępnym/niedostępnym Ace."""
    return {"ace": Tool("ace", Path("/usr/bin/ace"), "1.3.2", ready)}


def _report(accessible: bool) -> AceReport:
    messages = (
        []
        if accessible
        else [AceMessage(Severity.ERROR, "image-alt", "brak alt", "EPUB/ch1.xhtml")]
    )
    return AceReport(Path("b.epub"), accessible, "1.3.2", messages)


def test_a11y_exit_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Dostępny EPUB → exit 0."""
    monkeypatch.setattr(a11y, "detect_with_cache", lambda *a, **k: _tools(ready=True))
    monkeypatch.setattr(a11y, "run_ace", lambda *a, **k: _report(accessible=True))
    assert main(["a11y", str(tmp_path / "b.epub")]) == 0


def test_a11y_exit_inaccessible(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """EPUB z naruszeniami → exit 1."""
    monkeypatch.setattr(a11y, "detect_with_cache", lambda *a, **k: _tools(ready=True))
    monkeypatch.setattr(a11y, "run_ace", lambda *a, **k: _report(accessible=False))
    assert main(["a11y", str(tmp_path / "b.epub")]) == 1


def test_a11y_exit_no_tools(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Brak Ace → exit 2 (z instrukcją na stderr)."""
    monkeypatch.setattr(a11y, "detect_with_cache", lambda *a, **k: _tools(ready=False))
    assert main(["a11y", str(tmp_path / "b.epub")]) == 2


def test_a11y_writes_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Opcja --json zapisuje pełny raport do pliku."""
    monkeypatch.setattr(a11y, "detect_with_cache", lambda *a, **k: _tools(ready=True))
    monkeypatch.setattr(a11y, "run_ace", lambda *a, **k: _report(accessible=False))
    out = tmp_path / "report.json"
    assert main(["a11y", str(tmp_path / "b.epub"), "--json", str(out)]) == 1
    assert "image-alt" in out.read_text(encoding="utf-8")
