"""Uruchamianie zewnętrznych narzędzi (Sigil/Calibre) na pliku — wspólne dla zakładek.

Jedno miejsce z logiką ``subprocess.Popen`` (z ukryciem okna konsoli na Windows),
żeby zakładki Metadane i Edytor nie duplikowały uruchamiania narzędzi.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from epubforge.core import Tool
from epubforge.gui.workers import CREATE_NO_WINDOW


class ToolUnavailableError(RuntimeError):
    """Narzędzie nie zostało wykryte (brak dostępnej ścieżki)."""


def launch_tool(tool: Tool | None, target: Path) -> None:
    """Uruchamia narzędzie zewnętrzne na pliku ``target``.

    Args:
        tool: wykryte narzędzie (lub ``None``).
        target: plik przekazywany narzędziu jako argument.

    Raises:
        ToolUnavailableError: gdy narzędzie nie jest dostępne.
        OSError: gdy nie udało się uruchomić procesu.
    """
    if tool is None or not tool.available or tool.path is None:
        raise ToolUnavailableError
    subprocess.Popen([str(tool.path), str(target)], creationflags=CREATE_NO_WINDOW)
