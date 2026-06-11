"""Testy tooltipa reagującego na motyw."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import tkinter as tk
else:
    tk = pytest.importorskip("tkinter")

from epubforge.gui.theme import DARK, LIGHT, apply_theme
from epubforge.gui.widgets import Tooltip

pytestmark = pytest.mark.gui


@pytest.fixture
def root() -> Iterator[tk.Tk]:
    """Tworzy root tkinter albo pomija test, gdy środowisko nie ma display."""
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    window.withdraw()
    try:
        yield window
    finally:
        window.destroy()


def _tip_label_bg(tooltip: Tooltip) -> str:
    """Zwraca kolor tła etykiety wewnątrz okna tooltipa."""
    assert tooltip.tip_window is not None
    label = tooltip.tip_window.winfo_children()[0]
    return str(label.cget("bg"))


def test_tooltip_creates_without_error(root: tk.Tk) -> None:
    """Tooltip tworzy się, pokazuje i chowa bez błędu."""
    button = tk.Button(root, text="X")
    tooltip = Tooltip(button, "Pomoc")
    tooltip._show()
    assert tooltip.tip_window is not None
    tooltip._hide()
    assert tooltip.tip_window is None


def test_tooltip_empty_text_does_not_show(root: tk.Tk) -> None:
    """Pusty tekst → brak okienka."""
    tooltip = Tooltip(tk.Button(root, text="X"), "")
    tooltip._show()
    assert tooltip.tip_window is None


def test_tooltip_uses_current_theme_colors(root: tk.Tk) -> None:
    """Kolory tooltipa pochodzą z aktualnego motywu (light vs dark)."""
    button = tk.Button(root, text="X")
    tooltip = Tooltip(button, "Pomoc")

    apply_theme(root, LIGHT)
    tooltip._show()
    assert _tip_label_bg(tooltip) == LIGHT["bg3"]
    tooltip._hide()

    apply_theme(root, DARK)
    tooltip._show()
    assert _tip_label_bg(tooltip) == DARK["bg3"]
    tooltip._hide()
