"""Subkomenda CLI ``epubforge mobi``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

from epubforge.converters import MobiOptions, to_mobi
from epubforge.converters.to_mobi import MobiEngine, MobiFormat
from epubforge.core import ConversionError, ConverterNotFoundError
from epubforge.i18n import _


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``mobi`` w głównym parserze argparse."""
    parser = subparsers.add_parser("mobi", help=_("Konwertuj EPUB do MOBI/AZW3"))
    parser.add_argument("file", type=Path, help=_("Plik EPUB do konwersji"))
    parser.add_argument(
        "--format",
        dest="fmt",
        choices=("mobi", "azw3"),
        default="mobi",
        help=_("Format docelowy (domyślnie mobi)"),
    )
    parser.add_argument(
        "--engine",
        choices=("calibre", "kindlegen", "auto"),
        default="calibre",
        help=_("Silnik konwersji; Calibre zalecany, kindlegen wycofany (domyślnie calibre)"),
    )
    parser.add_argument(
        "--no-fix",
        dest="fix_epub_first",
        action="store_false",
        default=True,
        help=_("Nie uruchamiaj CSS fixera przed konwersją"),
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Uruchamia konwersję EPUB do MOBI/AZW3 z argumentów CLI."""
    options = MobiOptions(
        fmt=cast(MobiFormat, args.fmt),
        engine=cast(MobiEngine, args.engine),
        fix_epub_first=args.fix_epub_first,
    )
    target = args.file.with_suffix(f".{args.fmt}")
    try:
        result = to_mobi(args.file, target, options)
    except ConverterNotFoundError as exc:
        print(_("Błąd: {error}").format(error=exc), file=sys.stderr)
        return 2
    except ConversionError as exc:
        print(_("Błąd: {error}").format(error=exc), file=sys.stderr)
        return 1

    if result.log:
        print(result.log)
    print(_("Utworzono {format}: {path}").format(format=args.fmt.upper(), path=result.output_path))
    return 0
