"""Testy trwałości konfiguracji (:mod:`epubforge.core.config`)."""

from __future__ import annotations

from pathlib import Path

from epubforge.core.config import default_config_path, load_config, save_config


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
