"""Subkomenda CLI ``epubforge convert``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from epubforge.converters import ConversionError, ConverterNotFoundError, to_epub
from epubforge.i18n import _


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``convert`` w głównym parserze argparse."""
    parser = subparsers.add_parser(
        "convert",
        help=_("Konwertuj plik wejściowy do EPUB"),
        description=_(
            "Konwertuje plik do EPUB. Formaty Kindle (MOBI/AZW3/AZW/PRC) idą przez "
            "Calibre; pliki zabezpieczone DRM są odrzucane (EpubForge nie usuwa DRM)."
        ),
    )
    parser.add_argument(
        "source", type=Path, help=_("Plik wejściowy (TXT/MD/DOCX/HTML/PDF/MOBI/AZW3…)")
    )
    parser.add_argument("target", type=Path, help=_("Docelowy plik EPUB"))
    parser.add_argument(
        "--engine",
        choices=("pandoc", "calibre", "auto", "pdf2md"),
        default="auto",
        help=_("Silnik konwersji (domyślnie: auto; pdf2md tylko dla PDF)"),
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Uruchamia konwersję z argumentów CLI."""
    try:
        result = to_epub(args.source, args.target, engine=args.engine)
    except ConverterNotFoundError as exc:
        print(_("Błąd: {error}").format(error=exc), file=sys.stderr)
        return 2
    except ConversionError as exc:
        print(_("Błąd: {error}").format(error=exc), file=sys.stderr)
        return 1

    if result.log:
        print(result.log)
    print(_("Utworzono EPUB: {path}").format(path=result.output_path))
    return 0
