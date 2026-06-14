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
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from epubforge.core.config import (
    Config,
    config_dir,
    default_config_path,
    load_config,
    save_config,
)

# Flaga ukrywająca okno konsoli przy subprocess na Windows (pułapka #7).
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_VERSION_TIMEOUT = 10  # sekundy
_CACHE_MAX_AGE = timedelta(days=7)

# Minimalna wersja Javy wymagana przez EpubCheck 5.x.
_JAVA_MIN_MAJOR = 11
# Klucz w sekcji ``tools`` configu wskazujący ręcznie wybrany plik epubcheck.jar.
_EPUBCHECK_JAR_KEY = "epubcheck_jar"


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
    names = list(bases)
    if sys.platform == "win32":
        names = [*(f"{base}.exe" for base in bases), *names]
    return names


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
        base = Path(os.environ.get("APPDATA") or Path.home()) / "calibre"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Preferences" / "calibre"
    else:
        base = Path.home() / ".config" / "calibre"
    return base / "plugins"


def _parse_java_major(version_line: str) -> int | None:
    """Wyciąga główny numer wersji z linii ``java -version``.

    Obsługuje oba formaty: nowy (``"17.0.9"`` → 17) i stary (``"1.8.0_391"`` → 8,
    gdzie wiodące ``1.`` jest historycznym prefiksem). Zwraca ``None``, gdy nie da
    się sparsować.
    """
    match = re.search(r'version "([0-9][0-9._]*)"', version_line)
    if match is None:
        return None
    parts = match.group(1).replace("_", ".").split(".")
    try:
        if parts[0] == "1" and len(parts) > 1:
            return int(parts[1])
        return int(parts[0])
    except ValueError:
        return None


def _java_dirs() -> list[Path]:
    """Składa katalogi do przeszukania w poszukiwaniu ``java`` (poza ``PATH``)."""
    dirs: list[Path] = []
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        dirs.append(Path(java_home) / "bin")
    # %ProgramFiles%/Eclipse Adoptium/<jdk>/bin — typowa instalacja Temurin.
    for base in _env_dirs("Eclipse Adoptium"):
        if base.is_dir():
            dirs.extend(sorted(base.glob("*/bin")))
    dirs.append(Path("/usr/bin"))
    return dirs


def _detect_java() -> Tool:
    """Wykrywa ``java`` i sprawdza, czy wersja spełnia minimum dla EpubCheck."""
    path = _find_executable(_exe_names("java"), _java_dirs())
    if path is None:
        return Tool(name="java", path=None, version="", available=False)
    version_line = _get_version(path, ("-version",))  # java pisze na STDERR
    major = _parse_java_major(version_line)
    available = major is not None and major >= _JAVA_MIN_MAJOR
    return Tool(name="java", path=path, version=version_line, available=available)


def _epubcheck_jar_candidates(override: Path | None) -> list[Path]:
    """Składa listę kandydatów na plik ``epubcheck.jar`` w kolejności priorytetu."""
    candidates: list[Path] = []
    if override is not None:
        candidates.append(override)
    for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        root = os.environ.get(var)
        if root:
            candidates.extend(sorted(Path(root).glob("epubcheck*/epubcheck*.jar")))
    candidates.extend(sorted(Path.home().glob("epubcheck*/epubcheck*.jar")))
    candidates.append(config_dir() / "epubcheck" / "epubcheck.jar")
    if getattr(sys, "frozen", False):  # obok zamrożonego exe
        candidates.append(Path(sys.executable).parent / "epubcheck.jar")
    return candidates


def _epubcheck_version(jar: Path) -> str:
    """Czyta ``Implementation-Version`` z ``META-INF/MANIFEST.MF`` jara (bez Javy)."""
    try:
        with zipfile.ZipFile(jar) as archive:
            manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    except (OSError, KeyError, zipfile.BadZipFile):
        return ""
    for line in manifest.splitlines():
        if line.lower().startswith("implementation-version:"):
            return line.split(":", 1)[1].strip()
    return ""


def _detect_epubcheck(override: Path | None = None) -> Tool:
    """Wyszukuje ``epubcheck.jar`` i ustala jego wersję z manifestu."""
    for candidate in _epubcheck_jar_candidates(override):
        if candidate.is_file():
            return Tool(
                name="epubcheck",
                path=candidate,
                version=_epubcheck_version(candidate),
                available=True,
            )
    return Tool(name="epubcheck", path=None, version="", available=False)


class Tools:
    """Zbiór statycznych detektorów narzędzi zewnętrznych."""

    @staticmethod
    def java() -> Tool:
        """Wykrywa ``java`` (wymagane przez EpubCheck; wersja ≥ 11)."""
        return _detect_java()

    @staticmethod
    def epubcheck(jar_override: Path | None = None) -> Tool:
        """Wyszukuje ``epubcheck.jar`` (override → glob → config_dir → obok exe)."""
        return _detect_epubcheck(jar_override)

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
    def calibre_editor() -> Tool:
        """Wykrywa ``ebook-edit`` (edytor EPUB wbudowany w Calibre)."""
        return _make_tool(
            "calibre_editor",
            _exe_names("ebook-edit"),
            [
                *_env_dirs("Calibre2", "Calibre"),
                Path("/usr/bin"),
                Path("/opt/calibre"),
                Path("/Applications/calibre.app/Contents/MacOS"),
            ],
        )

    @staticmethod
    def sigil() -> Tool:
        """Wykrywa edytor EPUB Sigil.

        Wersji NIE ustalamy — Sigil na ``--version`` na moment pokazuje okno GUI
        (mignięcie przy pierwszej detekcji); interesuje nas tylko dostępność.
        """
        return _make_tool(
            "sigil",
            _exe_names("sigil", "Sigil"),
            [
                *_env_dirs("Sigil"),
                Path("/usr/bin"),
                Path("/opt/sigil"),
                Path("/Applications/Sigil.app/Contents/MacOS"),
            ],
            detect_version=False,
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
    def kindlegen() -> Tool:
        """Wykrywa ``kindlegen`` (generator MOBI firmy Amazon).

        UWAGA: ``kindlegen`` jest **oficjalnie wycofany** przez Amazon (ostatnia
        wersja 2.9 z 2018 r., brak dalszego rozwoju), ale nadal działa do
        generowania plików MOBI. Nowocześniejszą i zalecaną alternatywą jest
        Calibre ``ebook-convert``. Bywa też dołączany w katalogu Kindle Previewer 3.
        """
        return _make_tool(
            "kindlegen",
            _exe_names("kindlegen"),
            [
                *_env_dirs(
                    "KindleGen",
                    str(Path("Amazon") / "Kindle Previewer 3" / "lib" / "fc" / "bin"),
                ),
                Path("/usr/bin"),
                Path("/usr/local/bin"),
                Path("/opt/kindlegen"),
            ],
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
    def detect_all(epubcheck_jar: Path | None = None) -> dict[str, Tool]:
        """Uruchamia wszystkie detektory i zwraca mapę ``nazwa -> Tool``.

        Args:
            epubcheck_jar: ręcznie wskazany plik jara (override z configu).
        """
        return {
            "pandoc": Tools.pandoc(),
            "calibre_ebook_convert": Tools.calibre_ebook_convert(),
            "calibre_viewer": Tools.calibre_viewer(),
            "calibre_editor": Tools.calibre_editor(),
            "sigil": Tools.sigil(),
            "kindle_previewer": Tools.kindle_previewer(),
            "kindlegen": Tools.kindlegen(),
            "java": Tools.java(),
            "epubcheck": Tools.epubcheck(epubcheck_jar),
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


def _override_tool(name: str, path: Path) -> Tool:
    """Buduje :class:`Tool` z ręcznie wskazanej ścieżki (z detekcją wersji per typ).

    ``java`` i ``epubcheck`` mają własne ustalanie wersji/dostępności (Java ≥ 11,
    epubcheck z manifestu) — generyczne ``--version`` by je zepsuło.
    """
    if name == "java":
        version = _get_version(path, ("-version",)) if path.is_file() else ""
        major = _parse_java_major(version)
        ok = path.is_file() and major is not None and major >= _JAVA_MIN_MAJOR
        return Tool("java", path, version, ok)
    if name == "epubcheck":
        return _detect_epubcheck(path)
    exists = path.is_file()
    return Tool(
        name=name, path=path, version=_get_version(path) if exists else "", available=exists
    )


def _apply_overrides(tools: dict[str, Tool], overrides: dict[str, object]) -> None:
    """Nadpisuje ścieżki narzędzi wartościami z konfiguracji (ręczny override)."""
    for name, raw in overrides.items():
        if name not in tools or not isinstance(raw, str) or not raw:
            continue
        tools[name] = _override_tool(name, Path(raw))


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
    cached_tools = cached_tools if isinstance(cached_tools, dict) else {}
    # Override jara epubcheck żyje jako skalarny klucz w sekcji ``tools``.
    jar_override = _epubcheck_jar_override(cached_tools)

    if not force and _cache_is_fresh(config, max_age) and cached_tools:
        # Pomijamy skalarny klucz override — to nie jest serializowany Tool.
        tools = {
            name: _tool_from_dict(value)
            for name, value in cached_tools.items()
            if isinstance(value, dict)
        }
        _apply_overrides(tools, overrides)
        return tools

    tools = Tools.detect_all(epubcheck_jar=jar_override)
    _apply_overrides(tools, overrides)
    config["tools"] = {name: _tool_to_dict(tool) for name, tool in tools.items()}
    if jar_override is not None:  # zachowaj ręcznie wskazany jar między detekcjami
        config["tools"][_EPUBCHECK_JAR_KEY] = str(jar_override)
    config["kfx_plugin"] = Tools.calibre_kfx_plugin()
    config["last_detected"] = datetime.now(timezone.utc).isoformat()
    save_config(path, config)
    return tools


def _epubcheck_jar_override(cached_tools: dict[str, object]) -> Path | None:
    """Czyta ścieżkę ręcznie wskazanego jara z ``tools.epubcheck_jar`` (jeśli jest)."""
    raw = cached_tools.get(_EPUBCHECK_JAR_KEY)
    return Path(raw) if isinstance(raw, str) and raw else None
