"""Subkomenda CLI ``epubforge kfx``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

from epubforge.converters import KfxOptions, to_kfx
from epubforge.converters.to_kfx import KfxEngine
from epubforge.core import ConversionError, ConverterNotFoundError


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``kfx`` w głównym parserze argparse."""
    parser = subparsers.add_parser("kfx", help="Konwertuj EPUB do KFX")
    parser.add_argument("file", type=Path, help="Plik EPUB do konwersji")
    parser.add_argument(
        "--engine",
        choices=("calibre", "kindle-previewer"),
        default="auto",
        help="Silnik KFX; domyślnie auto: Calibre+KFX Output, potem Kindle Previewer",
    )
    parser.add_argument(
        "--no-fix",
        dest="fix_epub_first",
        action="store_false",
        default=True,
        help="Nie uruchamiaj CSS fixera przed konwersją",
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Uruchamia konwersję EPUB do KFX z argumentów CLI."""
    engine = cast(KfxEngine, args.engine)
    options = KfxOptions(engine=engine, fix_epub_first=args.fix_epub_first)
    try:
        result = to_kfx(args.file, args.file.parent, options)
    except ConverterNotFoundError as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 2
    except ConversionError as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1

    if result.log:
        print(result.log)
    print(f"Utworzono KFX: {result.output_path}")
    return 0
