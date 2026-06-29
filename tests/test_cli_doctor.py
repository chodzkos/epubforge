"""Testy CLI ``epubforge doctor`` i ``info`` — detekcja na żywo, świadomość platformy."""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from epubforge.cli import doctor
from epubforge.cli.main import main
from epubforge.core import Tool


def _full_tools() -> dict[str, Tool]:
    """Mapa 9 narzędzi: część dostępna, część brak (w tym narzędzia Windows/macOS)."""
    return {
        "pandoc": Tool("pandoc", Path("/usr/bin/pandoc"), "3.1.11", True),
        "calibre_ebook_convert": Tool("calibre_ebook_convert", None, "", False),
        "calibre_viewer": Tool("calibre_viewer", None, "", False),
        "calibre_editor": Tool("calibre_editor", None, "", False),
        "sigil": Tool("sigil", Path("/usr/bin/sigil"), "", True),
        "kindle_previewer": Tool("kindle_previewer", None, "", False),
        "kindlegen": Tool("kindlegen", None, "", False),
        "java": Tool("java", Path("/usr/bin/java"), "17.0.9", True),
        "epubcheck": Tool("epubcheck", None, "", False),
    }


def test_doctor_renders_full_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`doctor` renderuje sekcje System + Narzędzia i kończy się kodem 0."""
    monkeypatch.setattr(doctor, "console", Console(width=200))  # bez zawijania w tabeli
    monkeypatch.setattr(doctor, "detect_with_cache", lambda *a, **k: _full_tools())

    assert main(["doctor"]) == 0

    out = capsys.readouterr().out
    assert "System" in out
    assert "Narzędzia" in out
    assert "Pandoc" in out and "3.1.11" in out
    assert "Java" in out and "17.0.9" in out
    assert "✅" in out and "❌" in out


def test_doctor_forces_fresh_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    """`doctor` MUSI sondować na żywo: detect_with_cache(force=True), bez cache."""
    captured: dict[str, object] = {}

    def fake_detect(*args: object, **kwargs: object) -> dict[str, Tool]:
        captured["kwargs"] = kwargs
        return _full_tools()

    monkeypatch.setattr(doctor, "detect_with_cache", fake_detect)

    assert main(["doctor"]) == 0
    assert captured["kwargs"] == {"force": True}


def test_doctor_platform_restricted_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    """Na Linuksie brak Kindle Previewer/KindleGen to nota o platformie, NIE „❌ brak"."""
    monkeypatch.setattr(doctor.sys, "platform", "linux")
    monkeypatch.setattr(doctor.platform, "system", lambda: "Linux")

    missing_kp = Tool("kindle_previewer", None, "", False)
    missing_kindlegen = Tool("kindlegen", None, "", False)
    missing_pandoc = Tool("pandoc", None, "", False)

    assert "niedostępne na tej platformie" in doctor._status(missing_kp, "kindle_previewer")
    assert "niedostępne na tej platformie" in doctor._status(missing_kindlegen, "kindlegen")
    # Zwykłe narzędzie spoza listy platformowej dalej pokazuje „brak".
    assert "❌" in doctor._status(missing_pandoc, "pandoc")


def test_platform_restricted_shows_missing_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pod Windows Kindle Previewer może istnieć → brak to zwykłe „❌ brak", nie nota."""
    monkeypatch.setattr(doctor.sys, "platform", "win32")
    monkeypatch.setattr(doctor.platform, "system", lambda: "Windows")

    status = doctor._status(Tool("kindle_previewer", None, "", False), "kindle_previewer")
    assert "❌" in status
    assert "niedostępne na tej platformie" not in status


def test_status_available_shows_version_or_fallback() -> None:
    """Dostępne narzędzie: „✅ wersja"; bez wersji (np. Sigil) → „✅ dostępny"."""
    with_version = doctor._status(Tool("java", Path("/j"), "17", True), "java")
    no_version = doctor._status(Tool("sigil", Path("/s"), "", True), "sigil")
    assert with_version.startswith("✅") and "17" in with_version
    assert no_version.startswith("✅")


def test_info_lists_available_tools_live(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`info` (krótki wariant): wersja + lista dostępnych, sondowana na żywo (force=True)."""
    captured: dict[str, object] = {}

    def fake_detect(*args: object, **kwargs: object) -> dict[str, Tool]:
        captured["kwargs"] = kwargs
        return _full_tools()

    monkeypatch.setattr(doctor, "detect_with_cache", fake_detect)

    assert main(["info"]) == 0
    out = capsys.readouterr().out
    assert "EpubForge" in out
    assert "Dostępne narzędzia:" in out
    assert "Pandoc" in out and "Java" in out and "Sigil" in out
    assert "KindleGen" not in out  # niedostępne nie trafiają na listę
    assert captured["kwargs"] == {"force": True}


def test_info_no_tools_detected(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`info` gdy nic nie wykryto — czytelny komunikat zamiast pustej listy."""
    empty = {name: Tool(name, None, "", False) for name, _label in doctor._TOOL_LABELS}
    monkeypatch.setattr(doctor, "detect_with_cache", lambda *a, **k: empty)

    assert main(["info"]) == 0
    assert "Nie wykryto żadnych narzędzi." in capsys.readouterr().out
