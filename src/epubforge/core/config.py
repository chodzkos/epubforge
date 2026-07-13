"""Trwałość konfiguracji EpubForge — cienki adapter nad ``chodzkos_gui_kit.config``.

Logika (platformdirs, zapis atomowy, ``ConfigStore``/debounce) mieszka w kicie
``chodzkos-gui-kit`` (warstwa 0, czysty Python bez Qt — patrz ekstrakcja P1).
Tu zostaje glue specyficzne dla EpubForge:

* nazwa aplikacji ``"epubforge"`` dla :func:`config_dir`/:func:`default_config_path`;
* **kontrakt portable** (:func:`_is_portable`) i **lokalizacja configu**
  (:func:`config_dir`) — EpubForge jest tu źródłem prawdy, bo jego wariant
  portable jest samo-oznaczający (patrz niżej), a nie zależny od sidecara;
* migracja configu przy zmianie lokalizacji między wydaniami (:func:`_migrate_config`).

Kontrakt portable (jednoznaczny — audyt F-04):

* **portable** = zamrożony build ONEFILE oznaczony runtime hookiem
  (``build/rthook_portable.py`` ustawia ``sys._epubforge_portable = True``) →
  config leży **obok ``epubforge.exe``**, bez żadnego pliku-sidecara. Wydawany
  pojedynczy ``epubforge.exe`` jest więc naprawdę przenośny.
* **instalowany** = build ONEDIR / instalator (bez hooka) → config w lokalizacji
  systemowej (``%APPDATA%\\epubforge`` / ``~/.config/epubforge``).
* Dla zgodności wstecznej honorujemy też sidecar ``portable.flag`` obok exe
  (mechanizm kitu) — ale nie jest już dołączany do wydania.
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

# Atrybut na ``sys`` ustawiany przez runtime hook builda ONEFILE
# (``build/rthook_portable.py``). Jego obecność = wariant portable, bez sidecara.
_PORTABLE_ATTR = "_epubforge_portable"

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
    """Tryb portable: onefile oznaczony runtime hookiem albo (kompat) sidecar obok exe."""
    if not _is_frozen():
        return False
    if bool(getattr(sys, _PORTABLE_ATTR, False)):
        return True
    return (_exe_dir() / PORTABLE_MARKER).is_file()


def _installed_config_dir() -> Path:
    """Lokalizacja systemowa configu (``%APPDATA%``/``~/.config``) — wariant instalowany.

    Liczy ją kit (platformdirs z ``appauthor=False``/``roaming=True``). Wołamy ją
    tylko poza trybem portable, więc sidecar-owa gałąź kitu nas tu nie zaskoczy.
    """
    return _kit_config_dir(_APP_NAME)


def config_dir() -> Path:
    """Zwraca katalog konfiguracji EpubForge — jedyne źródło prawdy o lokalizacji."""
    if _is_portable():
        return _exe_dir()
    return _installed_config_dir()


def default_config_path() -> Path:
    """Zwraca domyślną ścieżkę ``config.json`` (z jednorazową migracją przy zmianie lokalizacji)."""
    path = config_dir() / "config.json"
    _migrate_config(path)
    return path


def _migration_source() -> Path | None:
    """Skąd skopiować config, gdy w bieżącej lokalizacji jeszcze go nie ma."""
    if _is_portable():
        # Nowy portable trzyma config OBOK exe — przejmij ustawienia z lokalizacji
        # systemowej, w której starszy „portable" (wydawany bez markera) błędnie
        # je trzymał. Dzięki temu aktualizacja nie gubi preferencji.
        return _installed_config_dir() / "config.json"
    # Wariant instalowany (config w %APPDATA%) — przejmij config spod exe, który
    # do v2.0 zamrożony build trzymał zawsze obok siebie.
    return _exe_dir() / "config.json"


def _migrate_config(target: Path) -> None:
    """Jednorazowo KOPIUJE config ze starej lokalizacji, gdy w nowej go brak.

    Kopiuje (nie przenosi) — oryginał zostaje nietknięty (może to być czyjś
    świadomy układ albo współdzielona instalacja), a aktualizacja nie gubi
    ustawień. Działa tylko w trybie frozen; w dev to no-op. Kit nie zna tej
    historii lokalizacji, więc glue zostaje tutaj.
    """
    if not _is_frozen() or target.exists():
        return
    source = _migration_source()
    if source is None or source == target or not source.is_file():
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        logger.info("Zmigrowano config %s → %s", source, target)
    except OSError as exc:
        logger.warning("Nie udało się zmigrować configu: %s", exc)
