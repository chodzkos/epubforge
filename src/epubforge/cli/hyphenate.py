"""Subkomenda CLI ``epubforge hyphenate``."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from epubforge.cli._batch import add_batch_arguments, format_dry_run, run_batch
from epubforge.core import Epub, EpubError
from epubforge.fixers import HyphenationOptions, hyphenate
from epubforge.fixers.hyphenator import HyphenationMethod
from epubforge.i18n import _


@dataclass(frozen=True)
class _HyphenatePayload:
    """Picklowalne opcje pracy dla pojedynczego pliku."""

    options: HyphenationOptions
    dry_run: bool
    diff_full: bool


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``hyphenate`` w głównym parserze argparse."""
    parser = subparsers.add_parser("hyphenate", help=_("Dodaj dzielenie wyrazów do EPUB"))
    add_batch_arguments(parser, file_help=_("Pliki EPUB do modyfikacji"))
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=_("Pokaż diff zmian bez zapisywania EPUB-a"),
    )
    parser.add_argument(
        "--diff-full",
        action="store_true",
        help=_("Nie skracaj diffów w trybie --dry-run"),
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
    payload = _HyphenatePayload(
        options=options,
        dry_run=args.dry_run,
        diff_full=args.diff_full,
    )
    return run_batch(
        args.files,
        jobs=args.jobs,
        handler=_run_hyphenate_for_path,
        payload=payload,
    )


def _run_hyphenate_for_path(path: Path, raw_payload: object) -> str:
    """Przetwarza jeden EPUB dla batch runnera."""
    payload = cast(_HyphenatePayload, raw_payload)
    try:
        with Epub(path) as epub:
            hyphenate(epub, payload.options)
            if payload.dry_run:
                return format_dry_run(epub, diff_full=payload.diff_full)
            epub.save()
    except EpubError as exc:
        raise RuntimeError(exc) from exc
    return _("Zaktualizowano EPUB: {path}").format(path=path)
