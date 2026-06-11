"""Audyt: kluczowe interaktywne kontrolki we wszystkich zakładkach mają tooltip.

Sprawdzamy klasy kontrolek (przyciski, radio, checkboxy, dropdowny, spinboxy,
menubuttony) — każda taka kontrolka powinna mieć powiązanie ``<Enter>`` od Tooltipa.
"""

# ruff: noqa: E402

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")

from epubforge.gui import app as app_module
from epubforge.gui.app import App

pytestmark = pytest.mark.gui

# Klasy ttk/tk uznawane za interaktywne kontrolki wymagające tooltipa.
_INTERACTIVE = {
    "TButton",
    "TRadiobutton",
    "TCheckbutton",
    "TCombobox",
    "TSpinbox",
    "TMenubutton",
}


def _walk(widget: tk.Misc) -> Iterator[tk.Misc]:
    """Iteruje rekurencyjnie po widgecie i jego potomkach."""
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _controls_without_tooltip(root: tk.Misc) -> list[str]:
    """Zwraca opisy kontrolek interaktywnych bez powiązania <Enter> (tooltipa)."""
    missing: list[str] = []
    for widget in _walk(root):
        if widget.winfo_class() in _INTERACTIVE and not widget.bind("<Enter>"):
            try:
                text = str(widget.cget("text"))
            except tk.TclError:
                text = ""
            missing.append(f"{widget.winfo_class()}({text}) @ {widget}")
    return missing


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[App]:
    """Tworzy App z mockowaną detekcją narzędzi albo pomija przy braku display."""
    monkeypatch.setattr(app_module, "detect_with_cache", lambda config_path: {})
    try:
        application = App(config_path=tmp_path / "config.json")
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    application.withdraw()
    try:
        yield application
    finally:
        application.destroy()


def test_all_controls_have_tooltips(app: App) -> None:
    """Wszystkie kontrolki interaktywne w głównym oknie mają tooltip."""
    missing = _controls_without_tooltip(app)
    assert missing == [], f"Kontrolki bez tooltipa: {missing}"


def test_about_dialog_controls_have_tooltips(app: App) -> None:
    """Kontrolki w oknie About także mają tooltipy."""
    app._open_about()
    assert app._about_window is not None
    missing = _controls_without_tooltip(app._about_window)
    assert missing == [], f"Kontrolki bez tooltipa (About): {missing}"
    app._close_about()
