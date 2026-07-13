"""Kontrola spójności kół: brak duplikatów + parzystość tree vs sdist.

Przyjmuje dwie ścieżki do plików ``*.whl``:

1. koło zbudowane ze **sdista** (domyślne ``uv build``),
2. koło zbudowane wprost z **drzewa** (``uv build --wheel``).

Sprawdza, że żadne z kół nie ma zdublowanych wpisów oraz że oba mają identyczny
zestaw plików — rozjazd oznacza, że build zależy od plików spoza sdista (np.
resztek w checkoutcie). Kod wyjścia 0 = OK; 1 = wykryto różnicę/duplikat.
"""

from __future__ import annotations

import sys
import zipfile
from collections import Counter
from pathlib import Path


def _entries(wheel: Path) -> list[str]:
    """Zwraca listę wpisów-plików koła (bez katalogów)."""
    with zipfile.ZipFile(wheel) as zf:
        return [name for name in zf.namelist() if not name.endswith("/")]


def _assert_no_duplicates(wheel: Path) -> None:
    """Przerywa, jeśli koło zawiera ten sam wpis więcej niż raz."""
    duplicates = [name for name, count in Counter(_entries(wheel)).items() if count > 1]
    if duplicates:
        raise SystemExit(f"{wheel.name}: zdublowane wpisy w kole: {sorted(duplicates)}")


def main(argv: list[str]) -> int:
    """Waliduje dwa koła: ``check_wheel_parity.py <from_sdist.whl> <from_tree.whl>``."""
    if len(argv) != 2:
        raise SystemExit("użycie: check_wheel_parity.py <koło_ze_sdista> <koło_z_drzewa>")
    from_sdist, from_tree = Path(argv[0]), Path(argv[1])

    for wheel in (from_sdist, from_tree):
        _assert_no_duplicates(wheel)
        print(f"OK: {wheel.name} — brak duplikatów")

    set_sdist, set_tree = set(_entries(from_sdist)), set(_entries(from_tree))
    if set_sdist != set_tree:
        only_sdist = sorted(set_sdist - set_tree)
        only_tree = sorted(set_tree - set_sdist)
        raise SystemExit(
            "rozjazd build-from-sdist vs build-from-tree:\n"
            f"  tylko w kole ze sdista: {only_sdist}\n"
            f"  tylko w kole z drzewa : {only_tree}"
        )
    print(f"OK: identyczny zestaw {len(set_sdist)} plików w obu kołach (sdist == tree)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
