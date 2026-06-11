"""Sprawdzenie środowiska przed lokalnym buildem Windows."""

from __future__ import annotations

import importlib

_REQUIRED_MODULES = {
    "PyInstaller": "pyinstaller",
    "PIL": "Pillow",
    "darkdetect": "darkdetect",
    "lxml.etree": "lxml",
    "pyphen": "pyphen",
    "tinycss2": "tinycss2",
    "tkinter": "tkinter",
    "tkinterdnd2": "tkinterdnd2",
}


def main() -> int:
    """Zwraca 0, gdy zależności buildu są kompletne."""
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
        print('Uruchom z katalogu repo: python -m pip install -e ".[build,gui]"')
        return 1

    # Import aplikacji łapie zależności ukryte w modułach GUI, np. darkdetect.
    importlib.import_module("epubforge.gui.app")
    print("[OK] Srodowisko buildu zawiera wymagane zaleznosci.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
