"""Subkomenda CLI ``epubforge fix``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from epubforge.core import Epub, EpubError
from epubforge.fixers import CssFixOptions, fix_css


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``fix`` w głównym parserze argparse."""
    parser = subparsers.add_parser("fix", help="Normalizuj CSS w EPUB")
    parser.add_argument("file", type=Path, help="Plik EPUB do modyfikacji")
    parser.add_argument("--remove-colors", action="store_true", help="Usuń kolory i tła z CSS")
    parser.add_argument("--remove-fonts", action="store_true", help="Usuń fonty z CSS i EPUB")
    parser.add_argument(
        "--no-reset",
        dest="inject_reset",
        action="store_false",
        default=True,
        help="Nie dodawaj resetu margin/padding",
    )
    parser.add_argument(
        "--replace-justify",
        action="store_true",
        help="Zamień text-align: justify na left",
    )
    parser.add_argument("--book-margin", type=int, help="Dodaj @page margin w px")
    parser.add_argument(
        "--keep-hyphenation-headers",
        dest="skip_hyphenation_headers",
        action="store_false",
        default=True,
        help="Nie dodawaj reguły h1-h3 { hyphens: none }",
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Uruchamia normalizację CSS z argumentów CLI."""
    options = CssFixOptions(
        remove_colors=args.remove_colors,
        remove_fonts=args.remove_fonts,
        inject_reset=args.inject_reset,
        replace_justify="left" if args.replace_justify else "keep",
        inject_book_margin_px=args.book_margin,
        skip_hyphenation_headers=args.skip_hyphenation_headers,
    )
    try:
        with Epub(args.file) as epub:
            fix_css(epub, options)
            epub.save()
    except EpubError as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1

    print(f"Zaktualizowano EPUB: {args.file}")
    return 0
