"""Sprawdzenie środowiska przed lokalnym buildem Windows."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_REQUIRED_MODULES = {
    "babel.messages.mofile": "babel",
    "PyInstaller": "pyinstaller",
    "PySide6.QtWidgets": "PySide6",
    "lxml.etree": "lxml",
    "pyphen": "pyphen",
    "tinycss2": "tinycss2",
    "platformdirs": "platformdirs",
}

_SRC_DIR = Path(__file__).resolve().parent.parent / "src" / "epubforge"
_LOCALE_DIR = _SRC_DIR / "locale"
_PRESETS_DIR = _SRC_DIR / "fixers" / "presets"
_STOPWORDS_DIR = _SRC_DIR / "stats_stopwords"
_HELP_DOCS_DIR = _SRC_DIR / "help_docs"


def main() -> int:
    """Zwraca 0, gdy zależności buildu są kompletne."""
    if sys.version_info < (3, 10):  # noqa: UP036 - ten helper ma zgłosić za starego Pythona.
        print(
            "[BLAD] EpubForge wymaga Pythona 3.10 lub nowszego "
            f"(uruchomiono {sys.version.split()[0]})."
        )
        print("Zainstaluj Python 3.12 i uruchom build przez build\\build.bat.")
        return 1

    missing: list[str] = []
    for module_name, package_name in _REQUIRED_MODULES.items():
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(package_name)

    if missing:
        print("[BLAD] Brakuje zaleznosci wymaganych do zbudowania kompletnego .exe:")
        for package_name in sorted(set(missing)):
            print(f"  - {package_name}")
        print()
        print('Uruchom z katalogu repo Pythonem 3.10+: python -m pip install -e ".[build,gui]"')
        return 1

    # Smoke import własnego motywu + aplikacji — łapie ukryte zależności GUI.
    importlib.import_module("epubforge.gui.theme")
    importlib.import_module("epubforge.gui.app")
    if not any(_LOCALE_DIR.glob("*/LC_MESSAGES/epubforge.mo")):
        print("[BLAD] Brak skompilowanych plikow locale (*.mo).")
        print("Uruchom: python build/compile_locales.py")
        return 1
    if not (_PRESETS_DIR / "presets.json").is_file() or not any(_PRESETS_DIR.glob("*.css")):
        print("[BLAD] Brak presetow CSS (fixers/presets/presets.json + *.css).")
        return 1
    if not all((_STOPWORDS_DIR / f"{lang}.txt").is_file() for lang in ("pl", "en", "de")):
        print("[BLAD] Brak stop-list statystyk (stats_stopwords/{pl,en,de}.txt).")
        return 1
    # Pliki prawdy pomocy (Markdown) — okno pomocy czyta je w runtime, więc frozen
    # exe musi je wozić (help_docs w datas). Sprawdzamy przez rejestr, nie glob.
    from epubforge.help_docs import MARKDOWN_SECTIONS

    if not all((_HELP_DOCS_DIR / filename).is_file() for _title, filename in MARKDOWN_SECTIONS):
        print("[BLAD] Brak plikow pomocy Markdown (help_docs/*.md z rejestru MARKDOWN_SECTIONS).")
        return 1
    print("[OK] Srodowisko buildu zawiera wymagane zaleznosci.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
