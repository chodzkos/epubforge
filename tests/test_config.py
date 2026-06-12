"""Testy trwałości konfiguracji (:mod:`epubforge.core.config`)."""

from __future__ import annotations

from pathlib import Path

import platformdirs
import pytest

from epubforge.core import config as config_mod
from epubforge.core.config import (
    ConfigStore,
    config_dir,
    default_config_path,
    load_config,
    save_config,
)


def test_roundtrip(tmp_path: Path) -> None:
    """Zapisana konfiguracja jest odczytywana w identycznej postaci."""
    path = tmp_path / "config.json"
    data = {"theme": "dark", "tools": {"pandoc": {"available": True}}, "count": 3}
    save_config(path, data)
    assert load_config(path) == data


def test_roundtrip_polish_chars(tmp_path: Path) -> None:
    """Polskie znaki w wartościach przechodzą roundtrip (ensure_ascii=False)."""
    path = tmp_path / "config.json"
    data = {"last_path": "/home/użytkownik/książki"}
    save_config(path, data)
    assert load_config(path)["last_path"] == "/home/użytkownik/książki"


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    """Brak pliku → pusty słownik (bez wyjątku)."""
    assert load_config(tmp_path / "nie_ma.json") == {}


def test_load_corrupt_returns_empty(tmp_path: Path) -> None:
    """Uszkodzony JSON → pusty słownik."""
    path = tmp_path / "bad.json"
    path.write_text("{to nie jest json", encoding="utf-8")
    assert load_config(path) == {}


def test_load_non_dict_returns_empty(tmp_path: Path) -> None:
    """JSON niebędący obiektem (np. lista) → pusty słownik."""
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_config(path) == {}


def test_save_creates_parent_dirs(tmp_path: Path) -> None:
    """save_config tworzy brakujące katalogi nadrzędne."""
    path = tmp_path / "a" / "b" / "config.json"
    save_config(path, {"x": 1})
    assert path.is_file()


def test_save_is_atomic_no_tmp_left(tmp_path: Path) -> None:
    """Po zapisie nie zostaje plik tymczasowy .tmp."""
    path = tmp_path / "config.json"
    save_config(path, {"x": 1})
    assert not (tmp_path / "config.json.tmp").exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_default_config_path_points_to_json() -> None:
    """Domyślna ścieżka kończy się na epubforge/config.json."""
    path = default_config_path()
    assert path.name == "config.json"
    assert path.parent.name == "epubforge"


# ── Lokalizacja przez platformdirs (regresja „zero migracji dla dev") ───────────


def test_config_dir_uses_platformdirs_roaming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Niezamrożony: config_dir == platformdirs.user_config_dir z dokładnymi parametrami.

    Sprawdza zgodność z dotychczasową lokalizacją (%APPDATA%\\epubforge /
    ~/.config/epubforge) — gwarancja braku migracji dla wersji deweloperskiej.
    """
    monkeypatch.setattr(config_mod.sys, "frozen", False, raising=False)
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


def test_config_dir_portable_uses_exe_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Frozen + portable.flag obok exe → config_dir == katalog exe."""
    exe = tmp_path / "epubforge.exe"
    exe.write_text("", encoding="utf-8")
    (tmp_path / "portable.flag").write_text("portable", encoding="utf-8")
    monkeypatch.setattr(config_mod.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config_mod.sys, "executable", str(exe))
    assert config_dir() == tmp_path


def test_frozen_without_marker_migrates_legacy_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Frozen bez markera: jednorazowa KOPIA starego configu spod exe; oryginał nietknięty."""
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


# ── ConfigStore: mark_dirty / flush / save_now ──────────────────────────────────


def test_store_mark_dirty_does_not_write(tmp_path: Path) -> None:
    """mark_dirty samo NIE zapisuje na dysk — tylko ustawia flagę."""
    path = tmp_path / "config.json"
    store = ConfigStore(path, {})
    store.mark_dirty()
    assert store.dirty is True
    assert not path.exists()


def test_store_flush_writes_when_dirty(tmp_path: Path) -> None:
    """flush zapisuje, gdy są zmiany, i czyści flagę."""
    path = tmp_path / "config.json"
    store = ConfigStore(path, {})
    store["theme"] = "light"  # __setitem__ oznacza brudne
    store.flush()
    assert load_config(path) == {"theme": "light"}
    assert store.dirty is False


def test_store_two_marks_one_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Dwa mark_dirty + jeden flush = dokładnie jeden zapis (debounce-friendly)."""
    path = tmp_path / "config.json"
    writes: list[int] = []
    original = config_mod.save_config
    monkeypatch.setattr(
        config_mod,
        "save_config",
        lambda p, data: (writes.append(1), original(p, data))[1],
    )

    store = ConfigStore(path, {})
    store.mark_dirty()
    store.mark_dirty()
    assert writes == []  # samo mark_dirty nic nie pisze
    store.flush()
    assert writes == [1]  # jeden flush = jeden zapis
    store.flush()
    assert writes == [1]  # bez nowych zmian flush nie pisze ponownie


def test_store_on_dirty_callback_fires(tmp_path: Path) -> None:
    """on_dirty jest wołany przy każdej zmianie (GUI podpina tu restart QTimera)."""
    path = tmp_path / "config.json"
    fired: list[int] = []
    store = ConfigStore(path, {}, on_dirty=lambda: fired.append(1))
    store["a"] = 1
    store.mark_dirty()
    assert len(fired) == 2


def test_store_save_now_writes_even_when_clean(tmp_path: Path) -> None:
    """save_now zapisuje bezwarunkowo (closeEvent woła to przy zamknięciu)."""
    path = tmp_path / "config.json"
    store = ConfigStore(path, {"x": 1})
    assert store.dirty is False
    store.save_now()
    assert load_config(path) == {"x": 1}
