"""Testy audytu dostępności DAISY Ace (parser, run_ace) — bez prawdziwego Ace."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from epubforge.core import ValidationError
from epubforge.validators import AceReport, Severity, parse_ace_report, run_ace
from epubforge.validators import ace as ace_module

_FIXTURES = Path(__file__).parent / "fixtures" / "ace"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


# ── Parser raportu ───────────────────────────────────────────────────────────


def test_parse_ok_report_is_accessible() -> None:
    """Raport bez naruszeń: dostępny, pusta lista komunikatów, wersja z pola."""
    report = parse_ace_report(_load("report_ok.json"), Path("book.epub"))
    assert report.accessible is True
    assert report.messages == []
    assert report.ace_version == "1.3.2"
    assert report.counts() == dict.fromkeys(Severity, 0)


def test_parse_violations_maps_severity() -> None:
    """critical/serious→error, moderate→warning, minor→info; „pass" pomijane."""
    report = parse_ace_report(_load("report_violations.json"), Path("book.epub"))
    counts = report.counts()
    assert counts[Severity.ERROR] == 2  # critical + serious
    assert counts[Severity.WARNING] == 1  # moderate
    assert counts[Severity.INFO] == 1  # minor (drugi „minor" ma outcome pass → pomijany)
    assert report.accessible is False


def test_parse_violations_rules_and_messages() -> None:
    """Reguły i treść naruszeń trafiają do AceMessage."""
    report = parse_ace_report(_load("report_violations.json"), Path("book.epub"))
    rules = {msg.rule for msg in report.messages}
    assert {"image-alt", "color-contrast", "epub-type-has-matching-role", "landmark-unique"} == rules
    image_alt = next(msg for msg in report.messages if msg.rule == "image-alt")
    assert "alt attribute" in image_alt.message


def test_parse_violations_internal_paths() -> None:
    """internal_path pochodzi z podmiotu testowego (lub z lokalizacji wyniku)."""
    report = parse_ace_report(_load("report_violations.json"), Path("book.epub"))
    by_rule = {msg.rule: msg.internal_path for msg in report.messages}
    assert by_rule["image-alt"] == "EPUB/text/chapter01.xhtml"
    # color-contrast ma własną lokalizację z fragmentem → ma pierwszeństwo, fragment ucięty.
    assert by_rule["color-contrast"] == "EPUB/text/chapter01.xhtml#h1"
    assert by_rule["epub-type-has-matching-role"] == "EPUB/text/chapter02.xhtml"


def test_parse_defensive_survives_messy_report() -> None:
    """Parser nie wywraca się na brakujących/niepoprawnych polach (defensywność)."""
    messy = {
        "assertions": [
            "nie-słownik",
            {"earl:testSubject": {"url": "EPUB/x.xhtml"}, "assertions": "też-nie-lista"},
            {
                "assertions": [
                    {"earl:test": {"dct:title": "rule-x", "earl:impact": "cthulhu"}},
                    {"earl:test": {}, "earl:result": {"earl:outcome": "fail"}},
                    "śmieć",
                ]
            },
        ]
    }
    report = parse_ace_report(messy, Path("book.epub"))
    # Nieznany impact „cthulhu" → info; brak outcome nie jest „pass" → liczy się.
    assert len(report.messages) == 2
    assert report.messages[0].severity is Severity.INFO
    assert report.ace_version == ""


def test_parse_flat_assertions() -> None:
    """Płaska lista naruszeń (bez zagnieżdżenia) też jest obsłużona."""
    flat = {
        "earl:testSubject": {"url": "EPUB/root.xhtml"},
        "assertions": [
            {
                "earl:test": {"dct:title": "html-lang-valid", "earl:impact": "serious"},
                "earl:result": {"earl:outcome": "fail", "dct:description": "Bad lang"},
            }
        ],
    }
    report = parse_ace_report(flat, Path("book.epub"))
    assert len(report.messages) == 1
    assert report.messages[0].severity is Severity.ERROR
    assert report.messages[0].internal_path == "EPUB/root.xhtml"


# ── run_ace (mock subprocess) ─────────────────────────────────────────────────


def _fake_run_factory(fixture: str | None, returncode: int):
    """Buduje atrapę subprocess.run, która zapisuje fixture do report.json w outdir."""

    def fake_run(cmd, **_kwargs):
        if fixture is not None:
            outdir = Path(cmd[cmd.index("--outdir") + 1])
            outdir.mkdir(parents=True, exist_ok=True)
            (outdir / "report.json").write_text(
                (_FIXTURES / fixture).read_text(encoding="utf-8"), encoding="utf-8"
            )
        return subprocess.CompletedProcess(cmd, returncode=returncode, stdout="", stderr="boom")

    return fake_run


def test_run_ace_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Poprawny JSON → raport dostępny."""
    monkeypatch.setattr(ace_module.subprocess, "run", _fake_run_factory("report_ok.json", 0))
    report = run_ace(tmp_path / "b.epub", Path("ace"))
    assert isinstance(report, AceReport)
    assert report.accessible is True
    assert report.ace_version == "1.3.2"


def test_run_ace_violations_returns_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Naruszenia (Ace zwraca kod != 0) to raport niedostępny, NIE wyjątek."""
    monkeypatch.setattr(
        ace_module.subprocess, "run", _fake_run_factory("report_violations.json", 1)
    )
    report = run_ace(tmp_path / "b.epub", Path("ace"))
    assert report.accessible is False
    assert len(report.messages) == 4


def test_run_ace_timeout_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Timeout procesu → ValidationError."""

    def raise_timeout(cmd, **_kwargs):
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(ace_module.subprocess, "run", raise_timeout)
    with pytest.raises(ValidationError):
        run_ace(tmp_path / "b.epub", Path("ace"))


def test_run_ace_no_json_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Ace nie utworzył raportu JSON → ValidationError ze stderr."""
    monkeypatch.setattr(ace_module.subprocess, "run", _fake_run_factory(None, 1))
    with pytest.raises(ValidationError, match="boom"):
        run_ace(tmp_path / "b.epub", Path("ace"))


def test_run_ace_broken_json_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Niepoprawny JSON → ValidationError."""
    monkeypatch.setattr(ace_module.subprocess, "run", _fake_run_factory("report_broken.json", 1))
    with pytest.raises(ValidationError):
        run_ace(tmp_path / "b.epub", Path("ace"))


def test_run_ace_missing_executable_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Brak pliku wykonywalnego (OSError) → ValidationError."""

    def raise_oserror(cmd, **_kwargs):
        raise OSError("not found")

    monkeypatch.setattr(ace_module.subprocess, "run", raise_oserror)
    with pytest.raises(ValidationError):
        run_ace(tmp_path / "b.epub", Path("ace"))
