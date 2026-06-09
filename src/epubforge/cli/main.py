"""Główny entry point CLI — będzie rozbudowany w kolejnych etapach."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import cast

from epubforge import __version__
from epubforge.cli import convert, fix, hyphenate


def main(argv: list[str] | None = None) -> int:
    """Punkt wejścia komendy `epubforge`.

    Args:
        argv: Lista argumentów (głównie do testowania). None = sys.argv.

    Returns:
        Kod wyjścia procesu (0 = OK).
    """
    parser = argparse.ArgumentParser(
        prog="epubforge",
        description="Modern toolkit for EPUB files — validate, fix, convert, hyphenate.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"epubforge {__version__}",
    )

    # Subkomendy będą dodane w etapach 1-7
    subparsers = parser.add_subparsers(dest="command", help="Dostępne komendy")
    subparsers.add_parser("info", help="Wyświetl informacje o wersji i wykrytych narzędziach")
    convert.add_parser(subparsers)
    fix.add_parser(subparsers)
    hyphenate.add_parser(subparsers)

    args = parser.parse_args(argv)

    if hasattr(args, "func"):
        handler = cast(Callable[[argparse.Namespace], int], args.func)
        return handler(args)

    if args.command == "info":
        print(f"EpubForge {__version__}")
        print("Wykryte narzędzia: (TODO - etap 3)")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
