"""Sprawdzenie środowiska przed lokalnym buildem Windows."""

from __future__ import annotations

import importlib
import sys

_REQUIRED_MODULES = {
    "PyInstaller": "pyinstaller",
    "PySide6.QtWidgets": "PySide6",
    "qdarktheme": "pyqtdarktheme-fork",
    "lxml.etree": "lxml",
    "pyphen": "pyphen",
    "tinycss2": "tinycss2",
}


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

    # Import aplikacji łapie zależności ukryte w modułach GUI (np. qdarktheme).
    importlib.import_module("epubforge.gui.app")
    print("[OK] Srodowisko buildu zawiera wymagane zaleznosci.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
