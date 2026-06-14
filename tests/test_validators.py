"""Testy walidatora EpubCheck (parser, run_epubcheck, detekcja wersji) — bez Javy."""

from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from epubforge.core import ValidationError
from epubforge.core.detection import (
    Tools,
    _detect_java,
    _epubcheck_version,
    _parse_java_major,
)
from epubforge.validators import Severity, parse_report, run_epubcheck
from epubforge.validators import epubcheck as ec

_FIXTURES = Path(__file__).parent / "fixtures" / "epubcheck"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


# ── Parser raportu ───────────────────────────────────────────────────────────


def test_parse_report_ok_has_no_messages() -> None:
    """Raport bez błędów: pusta lista komunikatów, wersja z checkera."""
    report = parse_report(_load("report_ok.json"), Path("book.epub"), valid=True)
    assert report.valid is True
    assert report.epubcheck_version == "5.1.0"
    assert report.messages == []
    assert report.counts() == dict.fromkeys(Severity, 0)


def test_parse_report_counts_and_severity_mapping() -> None:
    """Liczy komunikaty per severity; USAGE mapuje się na info."""
    report = parse_report(_load("report_errors.json"), Path("book.epub"), valid=False)
    counts = report.counts()
    assert counts[Severity.FATAL] == 1
    assert counts[Severity.ERROR] == 2
    assert counts[Severity.WARNING] == 1
    assert counts[Severity.INFO] == 1  # USAGE → info


def test_parse_report_normalizes_internal_paths() -> None:
    """Ścieżka „book.epub/OEBPS/ch1.xhtml" sprowadza się do wewnętrznej."""
    report = parse_report(_load("report_errors.json"), Path("book.epub"), valid=False)
    paths = [msg.internal_path for msg in report.messages]
    assert "OEBPS/content.opf" in paths
    assert "OEBPS/ch1.xhtml" in paths
    assert "OEBPS/ch2.xhtml" in paths  # już bez prefiksu — bez zmian


def test_parse_report_missing_locations_is_none() -> None:
    """Komunikat bez locations ma internal_path=None i line=None."""
    report = parse_report(_load("report_errors.json"), Path("book.epub"), valid=False)
    warning = next(msg for msg in report.messages if msg.code == "OPF-003")
    assert warning.internal_path is None
    assert warning.line is None


def test_parse_report_negative_column_becomes_none() -> None:
    """Kolumna -1 (brak) staje się None; dodatnia linia zostaje."""
    report = parse_report(_load("report_errors.json"), Path("book.epub"), valid=False)
    err2 = next(msg for msg in report.messages if msg.code == "RSC-006")
    assert err2.line == 20
    assert err2.column is None


# ── run_epubcheck (mock subprocess) ───────────────────────────────────────────


def _fake_run_factory(fixture: str | None, returncode: int):
    """Buduje atrapę subprocess.run, która zapisuje fixture do pliku raportu."""

    def fake_run(cmd, **_kwargs):
        if fixture is not None:
            Path(cmd[-1]).write_text((_FIXTURES / fixture).read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(cmd, returncode=returncode, stdout="", stderr="boom")

    return fake_run


def test_run_epubcheck_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Exit 0 + poprawny JSON → raport valid=True."""
    monkeypatch.setattr(ec.subprocess, "run", _fake_run_factory("report_ok.json", 0))
    report = run_epubcheck(tmp_path / "b.epub", Path("java"), Path("epubcheck.jar"))
    assert report.valid is True
    assert report.epubcheck_version == "5.1.0"


def test_run_epubcheck_invalid_returns_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Exit != 0 z poprawnym JSON to raport valid=False, NIE wyjątek."""
    monkeypatch.setattr(ec.subprocess, "run", _fake_run_factory("report_errors.json", 1))
    report = run_epubcheck(tmp_path / "b.epub", Path("java"), Path("epubcheck.jar"))
    assert report.valid is False
    assert len(report.messages) == 5


def test_run_epubcheck_timeout_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Timeout procesu → ValidationError."""

    def raise_timeout(cmd, **_kwargs):
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(ec.subprocess, "run", raise_timeout)
    with pytest.raises(ValidationError):
        run_epubcheck(tmp_path / "b.epub", Path("java"), Path("epubcheck.jar"))


def test_run_epubcheck_no_json_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Proces nie utworzył raportu JSON → ValidationError ze stderr."""
    monkeypatch.setattr(ec.subprocess, "run", _fake_run_factory(None, 1))
    with pytest.raises(ValidationError, match="boom"):
        run_epubcheck(tmp_path / "b.epub", Path("java"), Path("epubcheck.jar"))


def test_run_epubcheck_broken_json_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Niepoprawny JSON → ValidationError."""
    monkeypatch.setattr(ec.subprocess, "run", _fake_run_factory("report_broken.json", 1))
    with pytest.raises(ValidationError):
        run_epubcheck(tmp_path / "b.epub", Path("java"), Path("epubcheck.jar"))


# ── Detekcja wersji ────────────────────────────────────────────────────────--


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('openjdk version "17.0.9" 2023-10-17', 17),
        ('java version "1.8.0_391"', 8),
        ('openjdk version "11.0.21"', 11),
        ("garbage output", None),
    ],
)
def test_parse_java_major(line: str, expected: int | None) -> None:
    """Parser majora Javy obsługuje formaty 17.x i 1.8.x."""
    assert _parse_java_major(line) == expected


def test_detect_java_requires_min_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """Java 8 jest niedostępna (wymagane ≥ 11), Java 17 dostępna."""
    monkeypatch.setattr(
        "epubforge.core.detection._find_executable", lambda *_: Path("/usr/bin/java")
    )

    monkeypatch.setattr(
        "epubforge.core.detection._get_version", lambda *_: 'java version "1.8.0_391"'
    )
    assert _detect_java().available is False

    monkeypatch.setattr(
        "epubforge.core.detection._get_version", lambda *_: 'openjdk version "17.0.9"'
    )
    java = _detect_java()
    assert java.available is True
    assert java.path == Path("/usr/bin/java")


def _make_jar(path: Path, version: str | None) -> None:
    """Buduje mini-jar z opcjonalnym Implementation-Version w manifeście."""
    with zipfile.ZipFile(path, "w") as archive:
        manifest = "Manifest-Version: 1.0\r\n"
        if version is not None:
            manifest += f"Implementation-Version: {version}\r\n"
        archive.writestr("META-INF/MANIFEST.MF", manifest)


def test_epubcheck_version_from_manifest(tmp_path: Path) -> None:
    """Wersja epubchecka czytana z MANIFEST.MF bez uruchamiania Javy."""
    jar = tmp_path / "epubcheck.jar"
    _make_jar(jar, "5.1.0")
    assert _epubcheck_version(jar) == "5.1.0"


def test_epubcheck_detect_with_override(tmp_path: Path) -> None:
    """Override jara: Tools.epubcheck wskazuje plik i ustala wersję."""
    jar = tmp_path / "epubcheck.jar"
    _make_jar(jar, "5.1.0")
    tool = Tools.epubcheck(jar)
    assert tool.available is True
    assert tool.path == jar
    assert tool.version == "5.1.0"


def test_epubcheck_missing_jar_unavailable(tmp_path: Path) -> None:
    """Nieistniejący override → niedostępne (bez wyjątku)."""
    tool = Tools.epubcheck(tmp_path / "nope.jar")
    assert tool.available is False
