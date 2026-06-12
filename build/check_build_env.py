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

_LOCALE_DIR = Path(__file__).resolve().parent.parent / "src" / "epubforge" / "locale"


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
    print("[OK] Srodowisko buildu zawiera wymagane zaleznosci.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
