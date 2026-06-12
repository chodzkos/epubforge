"""Subkomenda CLI ``epubforge hyphenate``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

from epubforge.core import Epub, EpubError
from epubforge.fixers import HyphenationOptions, hyphenate
from epubforge.fixers.hyphenator import HyphenationMethod
from epubforge.i18n import _


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``hyphenate`` w głównym parserze argparse."""
    parser = subparsers.add_parser("hyphenate", help=_("Dodaj dzielenie wyrazów do EPUB"))
    parser.add_argument("file", type=Path, help=_("Plik EPUB do modyfikacji"))
    parser.add_argument("--lang", default="pl", help=_("Język słownika Pyphen (domyślnie: pl)"))
    parser.add_argument(
        "--method",
        choices=("soft-hyphen", "css"),
        default="soft-hyphen",
        help=_("Metoda dzielenia wyrazów (domyślnie: soft-hyphen)"),
    )
    header_group = parser.add_mutually_exclusive_group()
    header_group.add_argument(
        "--skip-headers",
        dest="skip_headers",
        action="store_true",
        default=True,
        help=_("Pomijaj nagłówki h1-h3 przy metodzie soft-hyphen (domyślnie)"),
    )
    header_group.add_argument(
        "--include-headers",
        dest="skip_headers",
        action="store_false",
        help=_("Dziel także nagłówki h1-h3 przy metodzie soft-hyphen"),
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Uruchamia dzielenie wyrazów z argumentów CLI."""
    method = cast(HyphenationMethod, args.method)
    options = HyphenationOptions(
        language=args.lang,
        method=method,
        skip_headers=args.skip_headers,
    )
    try:
        with Epub(args.file) as epub:
            hyphenate(epub, options)
            epub.save()
    except EpubError as exc:
        print(_("Błąd: {error}").format(error=exc), file=sys.stderr)
        return 1

    print(_("Zaktualizowano EPUB: {path}").format(path=args.file))
    return 0
