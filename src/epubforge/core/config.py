"""Trwałość konfiguracji EpubForge — cienki adapter nad ``chodzkos_gui_kit.config``.

Logika (platformdirs, zapis atomowy, ``ConfigStore``/debounce) mieszka w kicie
``chodzkos-gui-kit`` (warstwa 0, czysty Python bez Qt — patrz ekstrakcja P1).
Tu zostaje wyłącznie glue specyficzne dla EpubForge:

* nazwa aplikacji ``"epubforge"`` dla :func:`config_dir`/:func:`default_config_path`;
* jednorazowa migracja starego configu spod ``.exe`` (:func:`_migrate_legacy_config`),
  której kit świadomie nie zawiera (była specyficzna dla EpubForge).

Reszta (``load_config``, ``save_config``, ``ConfigStore``, ``PORTABLE_MARKER``)
jest re-eksportowana z kitu, żeby istniejący kod ``core``/``cli``/``gui`` nie
musiał znać ścieżki importu kitu.
"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path
from typing import Any

from chodzkos_gui_kit.config import (
    PORTABLE_MARKER,
    load_config,
    save_config,
)
from chodzkos_gui_kit.config import (
    Config as ConfigStore,
)
from chodzkos_gui_kit.config import (
    config_dir as _kit_config_dir,
)

logger = logging.getLogger(__name__)

# Luźny typ konfiguracji — serializowalny do JSON słownik. Zachowany dla
# istniejących adnotacji ``config: Config`` (przyjmują też zwykły ``dict``).
Config = dict[str, Any]

# Nazwa aplikacji dla platformdirs (GUI_STANDARD §8): %APPDATA%\epubforge /
# ~/.config/epubforge — zgodna z poprzednią lokalizacją, bez migracji ścieżek.
_APP_NAME = "epubforge"

__all__ = [
    "PORTABLE_MARKER",
    "Config",
    "ConfigStore",
    "config_dir",
    "default_config_path",
    "load_config",
    "save_config",
]


def _is_frozen() -> bool:
    """Czy działamy jako zamrożony ``.exe`` (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def _exe_dir() -> Path:
    """Katalog pliku wykonywalnego (sensowny tylko w trybie frozen)."""
    return Path(sys.executable).parent


def _is_portable() -> bool:
    """Tryb portable: zamrożony exe z markerem ``portable.flag`` obok."""
    return _is_frozen() and (_exe_dir() / PORTABLE_MARKER).is_file()


def config_dir() -> Path:
    """Zwraca katalog konfiguracji EpubForge (kit liczy lokalizację z nazwy app)."""
    return _kit_config_dir(_APP_NAME)


def default_config_path() -> Path:
    """Zwraca domyślną ścieżkę ``config.json`` (z jednorazową migracją legacy)."""
    path = config_dir() / "config.json"
    _migrate_legacy_config(path)
    return path


def _migrate_legacy_config(target: Path) -> None:
    """Kopiuje stary config spod exe do nowej lokalizacji (jednorazowo).

    Dotyczy tylko scenariusza frozen-bez-markera: do v2.0 zamrożony exe trzymał
    config zawsze obok siebie (utajony bug zapisu w ``Program Files`` dla wersji
    instalowanej). Jeśli nowy config jeszcze nie istnieje, a obok exe leży stary
    ``config.json`` — kopiujemy go (oryginału NIE kasujemy: to może być czyjś
    świadomy układ portable). Kit nie zna tej historii, więc glue zostaje tutaj.
    """
    if _is_portable() or not _is_frozen():
        return
    if target.exists():
        return
    legacy = _exe_dir() / "config.json"
    if not legacy.is_file():
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, target)
        logger.info("Zmigrowano config spod exe %s → %s", legacy, target)
    except OSError as exc:
        logger.warning("Nie udało się zmigrować configu spod exe: %s", exc)
