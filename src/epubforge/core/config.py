"""Trwałość konfiguracji aplikacji (``config.json``).

Lekki moduł bez zależności od reszty ``core`` (i bez Qt!) — przechowuje
ustawienia i cache wykrytych narzędzi. Lokalizację liczymy przez
``platformdirs`` (GUI_STANDARD v2.0 §8): jedna funkcja :func:`config_dir`
jest źródłem prawdy, wszyscy liczą od niej.

* zwykła instalacja → ``platformdirs.user_config_dir("epubforge", ...)``
  (``%APPDATA%\\epubforge`` na Windows, ``~/.config/epubforge`` na Linux,
  ``~/Library/Application Support/epubforge`` na macOS) — ścieżki Windows/Linux
  są identyczne z poprzednią wersją, więc migracja nie jest potrzebna;
* wariant portable (zamrożony ``.exe`` z plikiem-markerem ``portable.flag``
  obok) → config obok ``.exe``.

Zapis jest atomowy (plik tymczasowy + replace). :class:`ConfigStore` dokłada
debounce-friendly ``mark_dirty``/``flush`` (samo planowanie zapisu — QTimer —
żyje w GUI, tu nie ma żadnego Qt).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import platformdirs

logger = logging.getLogger(__name__)

# Typ konfiguracji — luźny słownik serializowalny do JSON.
Config = dict[str, Any]

# Marker wariantu portable — obecność tego pliku obok exe przełącza config
# z lokalizacji systemowej na katalog obok exe (build portable go tworzy).
PORTABLE_MARKER = "portable.flag"

# Nazwa aplikacji dla platformdirs. WAŻNE (GUI_STANDARD §8): dokładnie te
# parametry — appauthor=False (bez zdublowanego katalogu autora) i roaming=True
# (Roaming, nie Local) — dają %APPDATA%\epubforge / ~/.config/epubforge, czyli
# ścieżki zgodne z poprzednią wersją.
_APP_NAME = "epubforge"


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
    """Zwraca katalog konfiguracji — jedyne źródło prawdy o lokalizacji.

    * portable (frozen + marker) → katalog obok ``.exe``;
    * w pozostałych przypadkach → ``platformdirs.user_config_dir`` z parametrami
      zgodnymi z poprzednią lokalizacją (Roaming na Windows, ``~/.config`` na Linux).
    """
    if _is_portable():
        return _exe_dir()
    return Path(platformdirs.user_config_dir(_APP_NAME, appauthor=False, roaming=True))


def default_config_path() -> Path:
    """Zwraca domyślną ścieżkę ``config.json`` (liczoną od :func:`config_dir`).

    Przy okazji wykonuje jednorazową migrację configu z dawnej lokalizacji
    „obok exe" (zob. :func:`_migrate_legacy_config`).
    """
    path = config_dir() / "config.json"
    _migrate_legacy_config(path)
    return path


def _migrate_legacy_config(target: Path) -> None:
    """Kopiuje stary config spod exe do nowej lokalizacji (jednorazowo).

    Dotyczy tylko scenariusza frozen-bez-markera: do v2.0 zamrożony exe trzymał
    config zawsze obok siebie (utajony bug zapisu w ``Program Files`` dla wersji
    instalowanej). Jeśli nowy config jeszcze nie istnieje, a obok exe leży stary
    ``config.json`` — kopiujemy go (oryginału NIE kasujemy: to może być czyjś
    świadomy układ portable).
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


class ConfigStore(dict[str, Any]):
    """Konfiguracja jako słownik z flagą „brudne" i atomowym zapisem.

    Jest podtypem :class:`dict`, więc pasuje wszędzie, gdzie oczekiwany jest
    :data:`Config` — istniejące widgety zapisujące przez ``store[key] = ...``
    automatycznie oznaczają stan jako brudny.

    Debounce (odroczony zapis) realizuje GUI: ustawia ``on_dirty`` na callback
    restartujący ``QTimer``, który po ~1 s woła :meth:`flush`. Sam moduł nie zna
    Qt — trzyma tylko zwykły ``Callable``.
    """

    def __init__(
        self,
        path: Path,
        data: Config | None = None,
        on_dirty: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(data or {})  # init dict nie woła __setitem__ — start „czysty"
        self.path = path
        self.on_dirty = on_dirty
        self._dirty = False

    def __setitem__(self, key: str, value: Any) -> None:
        """Zapis klucza oznacza stan jako brudny (i odpala ``on_dirty``)."""
        super().__setitem__(key, value)
        self.mark_dirty()

    @property
    def dirty(self) -> bool:
        """Czy są niezapisane zmiany."""
        return self._dirty

    def mark_dirty(self) -> None:
        """Oznacza niezapisane zmiany i powiadamia ``on_dirty`` (jeśli ustawiony)."""
        self._dirty = True
        if self.on_dirty is not None:
            self.on_dirty()

    def flush(self) -> None:
        """Zapisuje na dysk TYLKO gdy są niezapisane zmiany."""
        if self._dirty:
            self.save_now()

    def save_now(self) -> None:
        """Zapisuje na dysk bezwarunkowo i czyści flagę (CLI / zamknięcie okna)."""
        save_config(self.path, dict(self))
        self._dirty = False
