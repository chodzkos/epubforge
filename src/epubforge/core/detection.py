"""Wykrywanie zewnętrznych narzędzi (Pandoc, Calibre, Sigil, Kindle Previewer).

Funkcje detekcji są **idempotentne** i pozbawione efektów ubocznych — czytają
tylko ``PATH`` i system plików, można je wołać wielokrotnie. Wynik można
zcache'ować w ``config.json`` (zob. :func:`detect_with_cache`) z ponowną
detekcją po 7 dniach.

Wersję narzędzia ustalamy przez ``--version`` z **timeoutem**; na Windows
proces uruchamiamy z flagą ``CREATE_NO_WINDOW``, żeby nie migało okno konsoli.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from epubforge.core.config import Config, default_config_path, load_config, save_config

# Flaga ukrywająca okno konsoli przy subprocess na Windows (pułapka #7).
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_VERSION_TIMEOUT = 10  # sekundy
_CACHE_MAX_AGE = timedelta(days=7)


@dataclass(frozen=True)
class Tool:
    """Opis wykrytego (lub nie) narzędzia zewnętrznego.

    Attributes:
        name: nazwa logiczna narzędzia (klucz w cache).
        path: ścieżka do pliku wykonywalnego lub ``None`` gdy nie znaleziono.
        version: pierwsza linia z ``--version`` lub pusty łańcuch.
        available: czy narzędzie jest dostępne (``path is not None``).
    """

    name: str
    path: Path | None
    version: str = ""
    available: bool = False


def _exe_names(*bases: str) -> list[str]:
    """Buduje listę nazw plików wykonywalnych z rozszerzeniem ``.exe`` na Windows."""
    if sys.platform == "win32":
        return [f"{base}.exe" for base in bases] + list(bases)
    return list(bases)


def _env_dirs(*subpaths: str) -> list[Path]:
    """Składa katalogi z typowych zmiennych środowiskowych Windows.

    Każdy ``subpath`` jest doklejany do wartości zmiennych Program Files /
    AppData. Zmienne nieistniejące są pomijane.
    """
    env_vars = ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA", "APPDATA")
    dirs: list[Path] = []
    for var in env_vars:
        root = os.environ.get(var)
        if not root:
            continue
        for sub in subpaths:
            dirs.append(Path(root) / sub)
    return dirs


def _find_executable(names: list[str], extra_dirs: list[Path]) -> Path | None:
    """Szuka pliku wykonywalnego najpierw w ``PATH``, potem w podanych katalogach.

    Args:
        names: kandydujące nazwy plików (z rozszerzeniem dla Windows).
        extra_dirs: dodatkowe katalogi instalacyjne do przeszukania.

    Returns:
        Ścieżka do pierwszego znalezionego pliku albo ``None``.
    """
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found)
    for directory in extra_dirs:
        for name in names:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def _get_version(path: Path, args: tuple[str, ...] = ("--version",)) -> str:
    """Zwraca pierwszą linię wyjścia ``path --version`` (lub puste, gdy błąd/timeout)."""
    try:
        result = subprocess.run(
            [str(path), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_VERSION_TIMEOUT,
            creationflags=_NO_WINDOW,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    output = f"{result.stdout or ''}{result.stderr or ''}".strip()
    return output.splitlines()[0].strip() if output else ""


def _make_tool(
    name: str,
    names: list[str],
    extra_dirs: list[Path],
    *,
    detect_version: bool = True,
) -> Tool:
    """Składa :class:`Tool` na podstawie wyniku wyszukiwania pliku wykonywalnego.

    Args:
        name: nazwa logiczna narzędzia.
        names: kandydujące nazwy plików.
        extra_dirs: dodatkowe katalogi instalacyjne.
        detect_version: czy uruchamiać ``--version`` (wyłącz dla narzędzi GUI,
            które na ``--version`` otwierają okno, np. Kindle Previewer).
    """
    path = _find_executable(names, extra_dirs)
    if path is None:
        return Tool(name=name, path=None, version="", available=False)
    version = _get_version(path) if detect_version else ""
    return Tool(name=name, path=path, version=version, available=True)


def _calibre_plugins_dir() -> Path:
    """Zwraca katalog wtyczek Calibre dla bieżącego systemu."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
        return base / "calibre" / "plugins"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Preferences" / "calibre" / "plugins"
    return Path.home() / ".config" / "calibre" / "plugins"


class Tools:
    """Zbiór statycznych detektorów narzędzi zewnętrznych."""

    @staticmethod
    def pandoc() -> Tool:
        """Wykrywa Pandoc (konwersje do/z wielu formatów)."""
        return _make_tool(
            "pandoc",
            _exe_names("pandoc"),
            [
                *_env_dirs("Pandoc"),
                Path("/usr/bin"),
                Path("/usr/local/bin"),
                Path("/opt/pandoc/bin"),
            ],
        )

    @staticmethod
    def calibre_ebook_convert() -> Tool:
        """Wykrywa ``ebook-convert`` z pakietu Calibre."""
        return _make_tool(
            "calibre_ebook_convert",
            _exe_names("ebook-convert"),
            [
                *_env_dirs("Calibre2", "Calibre"),
                Path("/usr/bin"),
                Path("/opt/calibre"),
                Path("/Applications/calibre.app/Contents/MacOS"),
            ],
        )

    @staticmethod
    def calibre_viewer() -> Tool:
        """Wykrywa ``ebook-viewer`` (podgląd EPUB w Calibre)."""
        return _make_tool(
            "calibre_viewer",
            _exe_names("ebook-viewer"),
            [
                *_env_dirs("Calibre2", "Calibre"),
                Path("/usr/bin"),
                Path("/opt/calibre"),
                Path("/Applications/calibre.app/Contents/MacOS"),
            ],
        )

    @staticmethod
    def sigil() -> Tool:
        """Wykrywa edytor EPUB Sigil."""
        return _make_tool(
            "sigil",
            _exe_names("sigil", "Sigil"),
            [
                *_env_dirs("Sigil"),
                Path("/usr/bin"),
                Path("/opt/sigil"),
                Path("/Applications/Sigil.app/Contents/MacOS"),
            ],
        )

    @staticmethod
    def kindle_previewer() -> Tool:
        """Wykrywa Kindle Previewer 3 (eksperymentalny silnik KFX).

        Wersji NIE ustalamy — KP3 na ``--version`` uruchamia GUI.
        """
        return _make_tool(
            "kindle_previewer",
            _exe_names("Kindle Previewer 3"),
            [
                *_env_dirs(str(Path("Amazon") / "Kindle Previewer 3")),
                Path("/Applications/Kindle Previewer 3.app/Contents/MacOS"),
            ],
            detect_version=False,
        )

    @staticmethod
    def calibre_kfx_plugin() -> bool:
        """Sprawdza, czy w katalogu wtyczek Calibre jest wtyczka KFX Output."""
        plugins_dir = _calibre_plugins_dir()
        if not plugins_dir.is_dir():
            return False
        if (plugins_dir / "KFX_Output.zip").is_file():
            return True
        return any(plugins_dir.glob("KFX Output*"))

    @staticmethod
    def detect_all() -> dict[str, Tool]:
        """Uruchamia wszystkie detektory i zwraca mapę ``nazwa -> Tool``."""
        return {
            "pandoc": Tools.pandoc(),
            "calibre_ebook_convert": Tools.calibre_ebook_convert(),
            "calibre_viewer": Tools.calibre_viewer(),
            "sigil": Tools.sigil(),
            "kindle_previewer": Tools.kindle_previewer(),
        }


def _tool_to_dict(tool: Tool) -> dict[str, object]:
    """Serializuje :class:`Tool` do słownika zapisywalnego w JSON."""
    return {
        "name": tool.name,
        "path": str(tool.path) if tool.path is not None else None,
        "version": tool.version,
        "available": tool.available,
    }


def _tool_from_dict(data: dict[str, object]) -> Tool:
    """Odtwarza :class:`Tool` z zapisanego słownika."""
    raw_path = data.get("path")
    path = Path(raw_path) if isinstance(raw_path, str) else None
    return Tool(
        name=str(data.get("name", "")),
        path=path,
        version=str(data.get("version", "")),
        available=bool(data.get("available", False)),
    )


def _apply_overrides(tools: dict[str, Tool], overrides: dict[str, object]) -> None:
    """Nadpisuje ścieżki narzędzi wartościami z konfiguracji (ręczny override)."""
    for name, raw in overrides.items():
        if name not in tools or not isinstance(raw, str) or not raw:
            continue
        path = Path(raw)
        exists = path.is_file()
        tools[name] = Tool(
            name=name,
            path=path,
            version=_get_version(path) if exists else "",
            available=exists,
        )


def _cache_is_fresh(config: Config, max_age: timedelta) -> bool:
    """Sprawdza, czy zapisany timestamp ``last_detected`` jest świeży."""
    last = config.get("last_detected")
    if not isinstance(last, str):
        return False
    try:
        detected_at = datetime.fromisoformat(last)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - detected_at < max_age


def detect_with_cache(
    config_path: Path | None = None,
    *,
    force: bool = False,
    max_age: timedelta = _CACHE_MAX_AGE,
) -> dict[str, Tool]:
    """Zwraca wykryte narzędzia, korzystając z cache w ``config.json``.

    Jeśli cache jest świeży (młodszy niż ``max_age``) i nie wymuszono detekcji,
    wynik jest czytany z konfiguracji. W przeciwnym razie uruchamiana jest pełna
    detekcja, a wynik (wraz z ``last_detected`` i statusem wtyczki KFX) zapisany.
    Ręczne nadpisania ścieżek z sekcji ``overrides`` są stosowane zawsze.

    Args:
        config_path: ścieżka pliku konfiguracyjnego (domyślnie systemowa).
        force: wymuś ponowną detekcję mimo świeżego cache.
        max_age: maksymalny wiek cache przed ponowną detekcją.

    Returns:
        Mapa ``nazwa -> Tool``.
    """
    path = config_path if config_path is not None else default_config_path()
    config = load_config(path)
    overrides = config.get("overrides")
    overrides = overrides if isinstance(overrides, dict) else {}

    cached_tools = config.get("tools")
    if not force and _cache_is_fresh(config, max_age) and isinstance(cached_tools, dict):
        tools = {name: _tool_from_dict(value) for name, value in cached_tools.items()}
        _apply_overrides(tools, overrides)
        return tools

    tools = Tools.detect_all()
    _apply_overrides(tools, overrides)
    config["tools"] = {name: _tool_to_dict(tool) for name, tool in tools.items()}
    config["kfx_plugin"] = Tools.calibre_kfx_plugin()
    config["last_detected"] = datetime.now(timezone.utc).isoformat()
    save_config(path, config)
    return tools
