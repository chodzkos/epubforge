"""Subkomenda CLI ``epubforge meta`` — podgląd i edycja metadanych EPUB."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from epubforge.core import Epub, EpubError, Metadata
from epubforge.i18n import _


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``meta`` w głównym parserze argparse."""
    parser = subparsers.add_parser("meta", help=_("Podgląd i edycja metadanych EPUB"))
    parser.add_argument("file", type=Path, help=_("Plik EPUB"))
    parser.add_argument("--title", help=_("Ustaw tytuł"))
    parser.add_argument(
        "--author", action="append", help=_("Ustaw autora (można podać wielokrotnie)")
    )
    parser.add_argument("--language", help=_("Ustaw kod języka (np. pl)"))
    parser.add_argument("--publisher", help=_("Ustaw wydawcę"))
    parser.add_argument("--date", help=_("Ustaw datę (ISO: RRRR-MM-DD)"))
    parser.add_argument("--isbn", help=_("Ustaw identyfikator (ISBN/UUID)"))
    parser.add_argument("--series", help=_("Ustaw nazwę cyklu (pusty łańcuch usuwa serię)"))
    parser.add_argument("--series-index", type=float, help=_("Ustaw numer tomu (np. 2 lub 1.5)"))
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Wyświetla metadane, a gdy podano flagi edycji — zapisuje zmiany."""
    try:
        with Epub(args.file) as epub:
            metadata = epub.metadata
            if _apply_edits(metadata, args):
                epub.metadata = metadata
                epub.save()
                print(_("Zapisano metadane: {path}\n").format(path=args.file))
            _print_metadata(metadata)
    except (EpubError, OSError, KeyError) as exc:
        print(_("Błąd: {error}").format(error=exc), file=sys.stderr)
        return 1
    return 0


def _apply_edits(metadata: Metadata, args: argparse.Namespace) -> bool:
    """Nakłada na metadane wartości z podanych flag; zwraca True, gdy coś zmieniono."""
    changed = False
    if args.title is not None:
        metadata.title = args.title
        changed = True
    if args.author is not None:
        metadata.creators = list(args.author)
        changed = True
    if args.language is not None:
        metadata.language = args.language
        changed = True
    if args.publisher is not None:
        metadata.publisher = args.publisher
        changed = True
    if args.date is not None:
        metadata.date = args.date
        changed = True
    if args.isbn is not None:
        metadata.identifier = args.isbn
        changed = True
    if args.series is not None:
        metadata.series = args.series
        changed = True
    if args.series_index is not None:
        metadata.series_index = args.series_index
        changed = True
    return changed


def _print_metadata(metadata: Metadata) -> None:
    """Wypisuje metadane w czytelnej formie."""
    empty = _("—")
    series = metadata.series or empty
    if metadata.series and metadata.series_index is not None:
        index = (
            str(int(metadata.series_index))
            if metadata.series_index.is_integer()
            else str(metadata.series_index)
        )
        series = f"{metadata.series} #{index}"
    print(_("Tytuł:    {value}").format(value=metadata.title or empty))
    print(_("Autorzy:  {value}").format(value=", ".join(metadata.creators) or empty))
    print(_("Język:    {value}").format(value=metadata.language or empty))
    print(_("Wydawca:  {value}").format(value=metadata.publisher or empty))
    print(_("Data:     {value}").format(value=metadata.date or empty))
    print(_("ISBN:     {value}").format(value=metadata.identifier or empty))
    print(_("Tematy:   {value}").format(value=", ".join(metadata.subjects) or empty))
    print(_("Cykl:     {value}").format(value=series))
