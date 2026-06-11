"""Strażnik migracji: warstwa GUI nie może już zależeć od tkinter."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gui

_GUI_DIR = Path(__file__).resolve().parents[2] / "src" / "epubforge" / "gui"


def test_gui_sources_contain_no_tkinter() -> None:
    """Żaden plik źródłowy GUI nie odwołuje się do tkinter/tkinterdnd2."""
    offenders: list[str] = []
    for path in _GUI_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "tkinter" in text or "tkdnd" in text:
            offenders.append(str(path))
    assert offenders == []


def test_importing_gui_does_not_pull_tkinter() -> None:
    """Import pakietu GUI nie ładuje modułu tkinter."""
    sys.modules.pop("tkinter", None)
    import epubforge.gui
    import epubforge.gui.app  # noqa: F401

    assert "tkinter" not in sys.modules
