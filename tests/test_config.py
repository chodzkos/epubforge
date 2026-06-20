"""Testy integracyjne configu EpubForge nad ``chodzkos_gui_kit.config``.

Logika trwałości (atomowy zapis, load/save, ``ConfigStore`` mark_dirty/flush)
mieszka w kicie i jest testowana tam (P1). Tu zostają wyłącznie zachowania
specyficzne dla EpubForge: nazwa aplikacji w lokalizacji configu oraz
jednorazowa migracja starego configu spod ``.exe``.
"""

from __future__ import annotations

from pathlib import Path

import platformdirs
import pytest

from epubforge.core import config as config_mod
from epubforge.core.config import config_dir, default_config_path, load_config


def test_default_config_path_points_to_epubforge_json() -> None:
    """Domyślna ścieżka kończy się na ``epubforge/config.json`` (nazwa app w kicie)."""
    path = default_config_path()
    assert path.name == "config.json"
    assert path.parent.name == "epubforge"


def test_config_dir_wires_epubforge_name_to_platformdirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """config_dir przekazuje do kitu nazwę ``epubforge`` + Roaming/appauthor=False.

    Gwarancja zgodności z dotychczasową lokalizacją (%APPDATA%\\epubforge /
    ~/.config/epubforge) — czyli brak migracji ścieżek po przejściu na kit.
    """
    captured: dict[str, object] = {}

    def fake_user_config_dir(name: str, *, appauthor: object, roaming: bool) -> str:
        captured["name"] = name
        captured["appauthor"] = appauthor
        captured["roaming"] = roaming
        return str(tmp_path / name)

    monkeypatch.setattr(platformdirs, "user_config_dir", fake_user_config_dir)

    result = config_dir()
    assert result == tmp_path / "epubforge"
    assert captured == {"name": "epubforge", "appauthor": False, "roaming": True}


def test_frozen_without_marker_migrates_legacy_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Frozen bez markera: jednorazowa KOPIA starego configu spod exe; oryginał nietknięty.

    Migracja jest glue specyficznym dla EpubForge (kit jej nie zawiera) — żyje
    w adapterze ``epubforge.core.config`` i tu ją testujemy.
    """
    exe_dir = tmp_path / "app"
    exe_dir.mkdir()
    exe = exe_dir / "epubforge.exe"
    exe.write_text("", encoding="utf-8")
    legacy = exe_dir / "config.json"
    legacy.write_text('{"theme": "dark"}', encoding="utf-8")

    new_dir = tmp_path / "roaming"
    monkeypatch.setattr(config_mod.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config_mod.sys, "executable", str(exe))
    monkeypatch.setattr(
        platformdirs,
        "user_config_dir",
        lambda *a, **k: str(new_dir / "epubforge"),
    )

    path = default_config_path()
    assert path == new_dir / "epubforge" / "config.json"
    assert path.is_file()  # skopiowany
    assert load_config(path) == {"theme": "dark"}
    assert legacy.is_file()  # oryginał nietknięty
