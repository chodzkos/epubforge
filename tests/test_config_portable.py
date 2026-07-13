"""Testy kontraktu portable vs instalator (symulacja zamrożonego ``.exe``).

Symulujemy frozen build przez podmianę ``sys.frozen``/``sys.executable`` oraz
atrybutu-markera runtime hooka (``sys._epubforge_portable``). Lokalizację
systemową (``%APPDATA%``) podmieniamy przez ``_kit_config_dir``. Sprawdzamy, że:

* onefile (portable) → config OBOK exe;
* onedir/instalator → config w lokalizacji systemowej;
* aktualizacja nie gubi ustawień (migracja KOPIUJE, nie nadpisuje istniejącego).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from epubforge.core import config as cfg


def _simulate_frozen(
    monkeypatch: pytest.MonkeyPatch,
    exe_dir: Path,
    *,
    portable: bool,
    appdata: Path,
) -> Path:
    """Ustawia frozen exe w ``exe_dir`` i podmienia lokalizację systemową na ``appdata``."""
    exe = exe_dir / "epubforge.exe"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text("", encoding="utf-8")
    monkeypatch.setattr(cfg.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cfg.sys, "executable", str(exe))
    monkeypatch.setattr(cfg.sys, cfg._PORTABLE_ATTR, portable, raising=False)
    monkeypatch.setattr(cfg, "_kit_config_dir", lambda _name: appdata)
    return exe


def test_portable_build_uses_dir_next_to_exe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Onefile z markerem runtime hooka → config leży obok exe (bez sidecara)."""
    exe_dir = tmp_path / "portable"
    _simulate_frozen(monkeypatch, exe_dir, portable=True, appdata=tmp_path / "appdata")
    assert cfg.config_dir() == exe_dir
    assert cfg.default_config_path() == exe_dir / "config.json"


def test_installer_build_uses_system_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Onedir/instalator (bez markera) → config w lokalizacji systemowej."""
    appdata = tmp_path / "appdata"
    _simulate_frozen(monkeypatch, tmp_path / "program_files", portable=False, appdata=appdata)
    assert cfg.config_dir() == appdata
    assert cfg.default_config_path() == appdata / "config.json"


def test_portable_update_migrates_config_from_system_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aktualizacja starego „portable" (config w %APPDATA%) → nowy portable przejmuje ustawienia."""
    exe_dir = tmp_path / "portable"
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    (appdata / "config.json").write_text('{"theme": "dark"}', encoding="utf-8")

    _simulate_frozen(monkeypatch, exe_dir, portable=True, appdata=appdata)

    path = cfg.default_config_path()
    assert path == exe_dir / "config.json"
    assert path.is_file()  # skopiowany obok exe
    assert cfg.load_config(path) == {"theme": "dark"}
    assert (appdata / "config.json").is_file()  # oryginał nietknięty


def test_installer_update_migrates_legacy_config_next_to_exe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Instalator: config spod exe (legacy do v2.0) kopiowany do lokalizacji systemowej."""
    exe_dir = tmp_path / "program_files"
    appdata = tmp_path / "appdata"
    _simulate_frozen(monkeypatch, exe_dir, portable=False, appdata=appdata)
    (exe_dir / "config.json").write_text('{"theme": "light"}', encoding="utf-8")

    path = cfg.default_config_path()
    assert path == appdata / "config.json"
    assert cfg.load_config(path) == {"theme": "light"}
    assert (exe_dir / "config.json").is_file()  # oryginał nietknięty


def test_portable_update_does_not_overwrite_existing_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gdy config już jest obok exe, migracja z %APPDATA% go NIE nadpisuje."""
    exe_dir = tmp_path / "portable"
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    (appdata / "config.json").write_text('{"theme": "dark"}', encoding="utf-8")
    _simulate_frozen(monkeypatch, exe_dir, portable=True, appdata=appdata)
    (exe_dir / "config.json").write_text('{"theme": "sepia"}', encoding="utf-8")

    path = cfg.default_config_path()
    assert cfg.load_config(path) == {"theme": "sepia"}  # zachowany, nie nadpisany


def test_portable_stable_across_update_keeps_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Portable→portable: lokalizacja configu (obok exe) nie zmienia się po aktualizacji."""
    exe_dir = tmp_path / "portable"
    _simulate_frozen(monkeypatch, exe_dir, portable=True, appdata=tmp_path / "appdata")
    (exe_dir / "config.json").write_text('{"theme": "dark"}', encoding="utf-8")
    # „Nowa wersja" exe w tym samym katalogu — ścieżka configu bez zmian.
    assert cfg.default_config_path() == exe_dir / "config.json"
    assert cfg.load_config(cfg.default_config_path()) == {"theme": "dark"}


def test_sidecar_still_forces_portable_for_backward_compat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zgodność wsteczna: sidecar ``portable.flag`` obok exe wymusza tryb portable."""
    exe_dir = tmp_path / "legacy-portable"
    _simulate_frozen(monkeypatch, exe_dir, portable=False, appdata=tmp_path / "appdata")
    (exe_dir / cfg.PORTABLE_MARKER).write_text("portable", encoding="utf-8")
    assert cfg.config_dir() == exe_dir


def test_non_frozen_dev_uses_system_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W dev (nie-frozen) config zawsze w lokalizacji systemowej, bez migracji."""
    appdata = tmp_path / "appdata"
    monkeypatch.setattr(cfg.sys, "frozen", False, raising=False)
    monkeypatch.setattr(cfg, "_kit_config_dir", lambda _name: appdata)
    assert cfg.config_dir() == appdata
    assert cfg.default_config_path() == appdata / "config.json"
