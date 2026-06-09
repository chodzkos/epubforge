"""Trwałość konfiguracji aplikacji (``config.json``).

Lekki moduł bez zależności od reszty ``core`` — przechowuje ustawienia
i cache wykrytych narzędzi. Zapis jest atomowy (plik tymczasowy + replace),
żeby przerwany zapis nie zostawił uszkodzonego pliku.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Typ konfiguracji — luźny słownik serializowalny do JSON.
Config = dict[str, Any]


def default_config_path() -> Path:
    """Zwraca domyślną lokalizację ``config.json``.

    * w zamrożonym ``.exe`` (PyInstaller) — obok pliku wykonywalnego;
    * na Windows — ``%APPDATA%/epubforge/config.json``;
    * w pozostałych systemach — ``$XDG_CONFIG_HOME`` lub ``~/.config``.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "config.json"
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "epubforge" / "config.json"


def load_config(path: Path) -> Config:
    """Wczytuje konfigurację z pliku JSON.

    Args:
        path: ścieżka do pliku konfiguracyjnego.

    Returns:
        Słownik konfiguracji; pusty słownik gdy plik nie istnieje albo
        jest uszkodzony (brak wyjątku — to nie jest sytuacja krytyczna).
    """
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(path: Path, config: Config) -> None:
    """Zapisuje konfigurację do pliku JSON w sposób atomowy.

    Tworzy brakujące katalogi nadrzędne. Zapis idzie najpierw do pliku
    ``.tmp``, a następnie :func:`os.replace` podmienia plik docelowy.

    Args:
        path: docelowa ścieżka pliku konfiguracyjnego.
        config: słownik do zapisania (musi być serializowalny do JSON).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
