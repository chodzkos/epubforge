"""Kompiluje katalogi gettext `.po` do `.mo`."""

from __future__ import annotations

from pathlib import Path

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po

_DOMAIN = "epubforge"
_LOCALE_DIR = Path(__file__).resolve().parent.parent / "src" / "epubforge" / "locale"


def compile_locales(locale_dir: Path = _LOCALE_DIR) -> list[Path]:
    """Kompiluje wszystkie pliki `.po` w katalogu locale."""
    outputs: list[Path] = []
    for po_path in sorted(locale_dir.glob(f"*/LC_MESSAGES/{_DOMAIN}.po")):
        mo_path = po_path.with_suffix(".mo")
        with po_path.open(encoding="utf-8") as po_file:
            catalog = read_po(po_file)
        mo_path.parent.mkdir(parents=True, exist_ok=True)
        with mo_path.open("wb") as mo_file:
            write_mo(mo_file, catalog)
        outputs.append(mo_path)
        print(f"compiled {mo_path}")
    return outputs


def main() -> int:
    """Entry point skryptu kompilującego."""
    outputs = compile_locales()
    if not outputs:
        print(f"no .po files found in {_LOCALE_DIR}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
