"""Testy CLI ``epubforge check`` — kody wyjścia (mock detekcji i run_epubcheck)."""

from __future__ import annotations

from pathlib import Path

import pytest

from epubforge.cli import check
from epubforge.cli.main import main
from epubforge.core import Tool
from epubforge.validators import Severity, ValidationMessage, ValidationReport


def _tools(*, ready: bool) -> dict[str, Tool]:
    """Zwraca mapę narzędzi z dostępną/niedostępną Javą i epubcheckiem."""
    return {
        "java": Tool("java", Path("/usr/bin/java"), "17", ready),
        "epubcheck": Tool("epubcheck", Path("/opt/epubcheck.jar"), "5.1.0", ready),
    }


def _report(valid: bool) -> ValidationReport:
    messages = (
        []
        if valid
        else [ValidationMessage(Severity.ERROR, "RSC-005", "boom", "OEBPS/ch1.xhtml", 3, 1)]
    )
    return ValidationReport(Path("b.epub"), valid, "5.1.0", messages)


def test_check_exit_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Poprawny EPUB → exit 0."""
    monkeypatch.setattr(check, "detect_with_cache", lambda *a, **k: _tools(ready=True))
    monkeypatch.setattr(check, "run_epubcheck", lambda *a, **k: _report(valid=True))
    assert main(["check", str(tmp_path / "b.epub")]) == 0


def test_check_exit_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """EPUB z błędami → exit 1."""
    monkeypatch.setattr(check, "detect_with_cache", lambda *a, **k: _tools(ready=True))
    monkeypatch.setattr(check, "run_epubcheck", lambda *a, **k: _report(valid=False))
    assert main(["check", str(tmp_path / "b.epub")]) == 1


def test_check_exit_no_tools(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Brak Javy/epubchecka → exit 2 (z instrukcją na stderr)."""
    monkeypatch.setattr(check, "detect_with_cache", lambda *a, **k: _tools(ready=False))
    assert main(["check", str(tmp_path / "b.epub")]) == 2


def test_check_writes_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Opcja --json zapisuje pełny raport do pliku."""
    monkeypatch.setattr(check, "detect_with_cache", lambda *a, **k: _tools(ready=True))
    monkeypatch.setattr(check, "run_epubcheck", lambda *a, **k: _report(valid=False))
    out = tmp_path / "report.json"
    assert main(["check", str(tmp_path / "b.epub"), "--json", str(out)]) == 1
    assert "RSC-005" in out.read_text(encoding="utf-8")
