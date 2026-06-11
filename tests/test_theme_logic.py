"""Testy logiki motywu (bez GUI) — detekcja systemu, rozwiązywanie ustawień.

Pasek tytułu Windows testujemy tylko w wariancie no-op (CI jest na Linuksie).
"""

from __future__ import annotations

import pytest

from epubforge.gui import window_theme
from epubforge.gui.theme import (
    DARK,
    LIGHT,
    resolve_theme_name,
    system_theme,
    theme_for_name,
)


def test_system_theme_dark(monkeypatch: pytest.MonkeyPatch) -> None:
    """darkdetect 'Dark' → 'dark'."""
    monkeypatch.setattr("epubforge.gui.theme.darkdetect.theme", lambda: "Dark")
    assert system_theme() == "dark"


def test_system_theme_light(monkeypatch: pytest.MonkeyPatch) -> None:
    """darkdetect 'Light' → 'light'."""
    monkeypatch.setattr("epubforge.gui.theme.darkdetect.theme", lambda: "Light")
    assert system_theme() == "light"


def test_system_theme_none_defaults_light(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gdy system nieznany (None) → 'light'."""
    monkeypatch.setattr("epubforge.gui.theme.darkdetect.theme", lambda: None)
    assert system_theme() == "light"


def test_resolve_explicit() -> None:
    """Jawne ustawienia mapują się wprost."""
    assert resolve_theme_name("dark") == "dark"
    assert resolve_theme_name("light") == "light"


def test_resolve_unknown_defaults_dark() -> None:
    """Nieznane ustawienie → dark."""
    assert resolve_theme_name("nonsense") == "dark"


def test_resolve_auto_uses_system(monkeypatch: pytest.MonkeyPatch) -> None:
    """'auto' korzysta z system_theme."""
    monkeypatch.setattr("epubforge.gui.theme.darkdetect.theme", lambda: "Dark")
    assert resolve_theme_name("auto") == "dark"
    monkeypatch.setattr("epubforge.gui.theme.darkdetect.theme", lambda: "Light")
    assert resolve_theme_name("auto") == "light"


def test_theme_for_name() -> None:
    """theme_for_name zwraca właściwy słownik."""
    assert theme_for_name("light") is LIGHT
    assert theme_for_name("dark") is DARK
    assert theme_for_name("cokolwiek") is DARK


def test_set_titlebar_dark_noop_off_windows() -> None:
    """Poza Windows set_titlebar_dark zwraca False bez efektów."""

    class _FakeWindow:
        def update_idletasks(self) -> None: ...
        def winfo_id(self) -> int:
            return 0

    # Na CI (Linux) zawsze False — nie dotykamy ctypes.
    import sys

    if sys.platform == "win32":
        pytest.skip("Test dotyczy zachowania poza Windows")
    assert window_theme.set_titlebar_dark(_FakeWindow(), True) is False  # type: ignore[arg-type]


def test_refresh_titlebar_noop_off_windows() -> None:
    """refresh_titlebar poza Windows nie rzuca i nic nie robi."""
    import sys

    if sys.platform == "win32":
        pytest.skip("Test dotyczy zachowania poza Windows")

    class _FakeWindow:
        def withdraw(self) -> None:
            raise AssertionError("nie powinno być wołane poza Windows")

        def deiconify(self) -> None:
            raise AssertionError("nie powinno być wołane poza Windows")

    window_theme.refresh_titlebar(_FakeWindow())  # type: ignore[arg-type]
