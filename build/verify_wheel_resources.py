"""Weryfikacja zasobów zainstalowanego koła przez publiczne API EpubForge.

Skrypt uruchamiamy w **pustym venv** z zainstalowanym kołem i **poza** drzewem
źródłowym repo — potwierdza, że dane (locale, presety CSS, receptury wbudowane,
stopwords, taksonomia PL) oraz marker ``py.typed`` są spakowane w kole i czytane
z zainstalowanej lokalizacji, a nie z checkoutu.

Same kontrole zasobów pochodzą z :mod:`epubforge._frozen_check` (jedno źródło
wspólne z samokontrolą zamrożonego ``.exe``). Tu dokładamy kontrole specyficzne
dla koła: pakiet z ``site-packages`` i obecny marker PEP 561.

Nie zależy od pytest — czysty ``python build/verify_wheel_resources.py``. Kod
wyjścia 0 = wszystkie zasoby odczytane; 1 = brak zasobu.
"""

from __future__ import annotations

import sys
from pathlib import Path

from epubforge._frozen_check import check_bundled_resources


def _check_not_from_checkout() -> None:
    """Pakiet musi pochodzić z instalacji (site-packages), nie z drzewa źródeł."""
    import epubforge

    pkg_dir = Path(epubforge.__file__).resolve().parent
    if "site-packages" not in pkg_dir.parts and "dist-packages" not in pkg_dir.parts:
        raise SystemExit(f"pakiet nie jest zainstalowany z koła (ścieżka: {pkg_dir})")


def _check_py_typed() -> None:
    """Marker PEP 561 musi leżeć obok zainstalowanego pakietu."""
    import epubforge

    marker = Path(epubforge.__file__).resolve().parent / "py.typed"
    if not marker.is_file():
        raise SystemExit(f"brak markera py.typed: {marker}")


def main() -> int:
    """Uruchamia kontrole koła + wspólne kontrole zasobów i raportuje wynik."""
    _check_not_from_checkout()
    print("OK: pakiet zainstalowany z koła (site-packages)")
    _check_py_typed()
    print("OK: marker py.typed obecny")
    for detail in check_bundled_resources():
        print(f"OK: {detail}")
    print("OK: wszystkie zasoby odczytane przez publiczne API zainstalowanego koła")
    return 0


if __name__ == "__main__":
    sys.exit(main())
