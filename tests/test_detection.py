"""Testy wykrywania narzędzi (:mod:`epubforge.core.detection`).

Wszystkie zależności od systemu (``PATH``, subprocess, katalogi wtyczek) są
mockowane — testy są deterministyczne i nie uruchamiają zewnętrznych binariów.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from epubforge.core import detection
from epubforge.core.config import load_config
from epubforge.core.detection import Tool, Tools, detect_with_cache

# ── Wyszukiwanie pliku wykonywalnego ───────────────────────────────────────────


def test_find_executable_via_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plik znaleziony przez shutil.which (PATH) ma pierwszeństwo."""
    monkeypatch.setattr(detection.shutil, "which", lambda name: "/usr/bin/pandoc")
    assert detection._find_executable(["pandoc"], []) == Path("/usr/bin/pandoc")


def test_find_executable_in_extra_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Gdy nie ma w PATH — szukamy w katalogach instalacyjnych."""
    monkeypatch.setattr(detection.shutil, "which", lambda name: None)
    (tmp_path / "pandoc").write_text("#!/bin/sh\n", encoding="utf-8")
    assert detection._find_executable(["pandoc"], [tmp_path]) == tmp_path / "pandoc"


def test_find_executable_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brak w PATH i w katalogach → None."""
    monkeypatch.setattr(detection.shutil, "which", lambda name: None)
    assert detection._find_executable(["pandoc"], [Path("/nope")]) is None


# ── Wersja przez subprocess ─────────────────────────────────────────────────────


def _fake_run(stdout: str = "", stderr: str = ""):  # type: ignore[no-untyped-def]
    def runner(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=0)

    return runner


def test_get_version_first_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """_get_version zwraca pierwszą, przyciętą linię wyjścia."""
    monkeypatch.setattr(detection.subprocess, "run", _fake_run(stdout="pandoc 3.1.2\nfeatures..."))
    assert detection._get_version(Path("/usr/bin/pandoc")) == "pandoc 3.1.2"


def test_get_version_from_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wersja wypisywana na stderr też jest wychwytywana."""
    monkeypatch.setattr(detection.subprocess, "run", _fake_run(stderr="tool v1.0"))
    assert detection._get_version(Path("/x")) == "tool v1.0"


def test_get_version_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Timeout subprocess → pusty łańcuch (bez wyjątku)."""

    def boom(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="x", timeout=10)

    monkeypatch.setattr(detection.subprocess, "run", boom)
    assert detection._get_version(Path("/x")) == ""


def test_get_version_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brak binarki (OSError) → pusty łańcuch."""

    def boom(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(detection.subprocess, "run", boom)
    assert detection._get_version(Path("/x")) == ""


# ── Detektory Tools ─────────────────────────────────────────────────────────────


def test_pandoc_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pandoc obecny w PATH → available z wersją."""
    monkeypatch.setattr(detection, "_find_executable", lambda names, dirs: Path("/usr/bin/pandoc"))
    monkeypatch.setattr(detection, "_get_version", lambda path: "pandoc 3.1.2")
    tool = Tools.pandoc()
    assert tool.available is True
    assert tool.path == Path("/usr/bin/pandoc")
    assert tool.version == "pandoc 3.1.2"


def test_tool_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brak narzędzia → Tool(available=False, path=None)."""
    monkeypatch.setattr(detection, "_find_executable", lambda names, dirs: None)
    tool = Tools.calibre_ebook_convert()
    assert tool.available is False
    assert tool.path is None
    assert tool.version == ""


def test_calibre_editor_available_via_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calibre Editor obecny w PATH → available z wersją."""
    which_calls: list[str] = []

    def fake_which(name: str) -> str | None:
        which_calls.append(name)
        if name in {"ebook-edit", "ebook-edit.exe"}:
            return "/usr/bin/ebook-edit"
        return None

    monkeypatch.setattr(detection.shutil, "which", fake_which)
    monkeypatch.setattr(detection, "_get_version", lambda path: "ebook-edit 7.0")
    tool = Tools.calibre_editor()
    assert tool.available is True
    assert tool.path == Path("/usr/bin/ebook-edit")
    assert tool.version == "ebook-edit 7.0"
    assert any(name in {"ebook-edit", "ebook-edit.exe"} for name in which_calls)


def test_calibre_editor_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brak ebook-edit w PATH i typowych lokalizacjach → unavailable."""
    monkeypatch.setattr(detection.shutil, "which", lambda name: None)
    monkeypatch.setattr(Path, "is_file", lambda self: False)

    def fail(path: Path) -> str:
        raise AssertionError("--version nie powinno być wywołane dla brakującej binarki")

    monkeypatch.setattr(detection, "_get_version", fail)
    tool = Tools.calibre_editor()
    assert tool.available is False
    assert tool.path is None
    assert tool.version == ""


def test_kindle_previewer_skips_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dla Kindle Previewer NIE uruchamiamy --version (otwiera GUI)."""
    monkeypatch.setattr(detection, "_find_executable", lambda names, dirs: Path("/x/kp3"))

    def fail(path: Path) -> str:
        raise AssertionError("--version nie powinno być wywołane dla KP3")

    monkeypatch.setattr(detection, "_get_version", fail)
    tool = Tools.kindle_previewer()
    assert tool.available is True
    assert tool.version == ""


def test_kindlegen_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """kindlegen obecny w PATH → available z wersją."""
    monkeypatch.setattr(detection, "_find_executable", lambda names, dirs: Path("/bin/kindlegen"))
    monkeypatch.setattr(detection, "_get_version", lambda path: "kindlegen 2.9")
    tool = Tools.kindlegen()
    assert tool.available is True
    assert tool.path == Path("/bin/kindlegen")
    assert tool.version == "kindlegen 2.9"


def test_kindlegen_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brak kindlegen → Tool(available=False)."""
    monkeypatch.setattr(detection, "_find_executable", lambda names, dirs: None)
    assert Tools.kindlegen().available is False


def test_detect_all_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """detect_all zwraca komplet narzędzi jako Tool."""
    monkeypatch.setattr(detection, "_find_executable", lambda names, dirs: None)
    tools = Tools.detect_all()
    assert set(tools) == {
        "pandoc",
        "calibre_ebook_convert",
        "calibre_viewer",
        "calibre_editor",
        "sigil",
        "kindle_previewer",
        "kindlegen",
    }
    assert all(isinstance(t, Tool) for t in tools.values())


# ── Wtyczka KFX ─────────────────────────────────────────────────────────────────


def test_kfx_plugin_zip_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """KFX_Output.zip w katalogu wtyczek → True."""
    monkeypatch.setattr(detection, "_calibre_plugins_dir", lambda: tmp_path)
    (tmp_path / "KFX_Output.zip").write_bytes(b"x")
    assert Tools.calibre_kfx_plugin() is True


def test_kfx_plugin_glob_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Plik pasujący do 'KFX Output*' → True."""
    monkeypatch.setattr(detection, "_calibre_plugins_dir", lambda: tmp_path)
    (tmp_path / "KFX Output v2.zip").write_bytes(b"x")
    assert Tools.calibre_kfx_plugin() is True


def test_kfx_plugin_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pusty katalog wtyczek → False."""
    monkeypatch.setattr(detection, "_calibre_plugins_dir", lambda: tmp_path)
    assert Tools.calibre_kfx_plugin() is False


def test_kfx_plugin_dir_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nieistniejący katalog wtyczek → False."""
    monkeypatch.setattr(detection, "_calibre_plugins_dir", lambda: tmp_path / "brak")
    assert Tools.calibre_kfx_plugin() is False


# ── Cache w config.json ─────────────────────────────────────────────────────────


@pytest.fixture
def no_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wszystkie narzędzia niewykryte, wtyczka KFX nieobecna."""
    monkeypatch.setattr(detection, "_find_executable", lambda names, dirs: None)
    monkeypatch.setattr(Tools, "calibre_kfx_plugin", staticmethod(lambda: False))


def test_detect_with_cache_writes(tmp_path: Path, no_tools: None) -> None:
    """Pierwsza detekcja zapisuje cache z timestampem i statusem wtyczki."""
    cfg = tmp_path / "config.json"
    tools = detect_with_cache(cfg, force=True)
    assert set(tools) == {
        "pandoc",
        "calibre_ebook_convert",
        "calibre_viewer",
        "calibre_editor",
        "sigil",
        "kindle_previewer",
        "kindlegen",
    }
    saved = load_config(cfg)
    assert "last_detected" in saved
    assert saved["kfx_plugin"] is False
    assert "pandoc" in saved["tools"]


def test_detect_with_cache_uses_fresh_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Świeży cache jest używany — detect_all NIE jest wywoływane ponownie."""
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(detection, "_find_executable", lambda names, dirs: None)
    monkeypatch.setattr(Tools, "calibre_kfx_plugin", staticmethod(lambda: False))
    detect_with_cache(cfg, force=True)

    def fail() -> dict[str, Tool]:
        raise AssertionError("detect_all nie powinno zostać wywołane przy świeżym cache")

    monkeypatch.setattr(Tools, "detect_all", staticmethod(fail))
    tools = detect_with_cache(cfg)  # bez force → z cache
    assert "pandoc" in tools


def test_detect_with_cache_stale_redetects(tmp_path: Path, no_tools: None) -> None:
    """Cache starszy niż max_age wymusza ponowną detekcję."""
    cfg = tmp_path / "config.json"
    detect_with_cache(cfg, force=True)
    # Cofnij timestamp o 10 dni.
    config = load_config(cfg)
    config["last_detected"] = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    from epubforge.core.config import save_config

    save_config(cfg, config)
    # Świeżość 7 dni → przeterminowane, detekcja rusza ponownie i nadpisuje timestamp.
    detect_with_cache(cfg)
    refreshed = load_config(cfg)
    assert refreshed["last_detected"] != config["last_detected"]


def test_manual_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ręczny override ścieżki z config jest stosowany."""
    monkeypatch.setattr(detection, "_find_executable", lambda names, dirs: None)
    monkeypatch.setattr(Tools, "calibre_kfx_plugin", staticmethod(lambda: False))
    monkeypatch.setattr(detection, "_get_version", lambda path: "custom 1.0")
    custom = tmp_path / "my-pandoc"
    custom.write_text("#!/bin/sh\n", encoding="utf-8")
    cfg = tmp_path / "config.json"
    from epubforge.core.config import save_config

    save_config(cfg, {"overrides": {"pandoc": str(custom)}})
    tools = detect_with_cache(cfg, force=True)
    assert tools["pandoc"].path == custom
    assert tools["pandoc"].available is True
    assert tools["pandoc"].version == "custom 1.0"
