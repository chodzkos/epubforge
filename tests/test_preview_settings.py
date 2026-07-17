"""Testy adaptera ustawień podglądu (czysty Python, bez Qt)."""

from __future__ import annotations

from pathlib import Path

from epubforge.core import ConfigStore
from epubforge.gui.preview.settings import (
    BACKEND_KEY,
    PROFILE_KEY,
    SPLIT_VIEW_KEY,
    PreviewSettings,
)


def test_defaults_without_store() -> None:
    """Bez configu adapter zwraca sensowne domyślne (auto / brak podziału)."""
    settings = PreviewSettings()
    assert settings.backend == "auto"
    assert settings.split_view is False
    assert settings.profile == "default"


def test_invalid_backend_is_clamped_to_auto() -> None:
    """Nieznana wartość backendu nie trafia do configu — klamrujemy do auto."""
    settings = PreviewSettings({BACKEND_KEY: "nonsense"})
    assert settings.backend == "auto"
    settings.backend = "also-nonsense"
    assert settings.backend == "auto"


def test_assignment_writes_top_level_keys() -> None:
    """Zapis idzie przez przypisanie klucza najwyższego poziomu (bez zagnieżdżeń)."""
    store: dict[str, object] = {}
    settings = PreviewSettings(store)
    settings.backend = "webengine"
    settings.split_view = True
    settings.profile = "phone"
    assert store == {
        BACKEND_KEY: "webengine",
        SPLIT_VIEW_KEY: True,
        PROFILE_KEY: "phone",
    }


def test_configstore_marks_dirty_and_persists(tmp_path: Path) -> None:
    """Przez istniejący ConfigStore zapis oznacza brud (on_dirty) i utrwala się."""
    store = ConfigStore("epubforge", path=tmp_path / "config.json")
    fired: list[str] = []
    store.on_dirty = lambda: fired.append("dirty")

    settings = PreviewSettings(store)
    settings.backend = "text"

    assert store[BACKEND_KEY] == "text"
    assert fired, "przypisanie klucza powinno wywołać on_dirty (debounce GUI)"
    store.save_now()
    reloaded = ConfigStore("epubforge", path=tmp_path / "config.json")
    assert reloaded[BACKEND_KEY] == "text"
