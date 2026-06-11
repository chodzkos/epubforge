"""Subkomenda CLI ``epubforge meta`` — podgląd i edycja metadanych EPUB."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from epubforge.core import Epub, EpubError, Metadata


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``meta`` w głównym parserze argparse."""
    parser = subparsers.add_parser("meta", help="Podgląd i edycja metadanych EPUB")
    parser.add_argument("file", type=Path, help="Plik EPUB")
    parser.add_argument("--title", help="Ustaw tytuł")
    parser.add_argument("--author", action="append", help="Ustaw autora (można podać wielokrotnie)")
    parser.add_argument("--language", help="Ustaw kod języka (np. pl)")
    parser.add_argument("--publisher", help="Ustaw wydawcę")
    parser.add_argument("--date", help="Ustaw datę (ISO: RRRR-MM-DD)")
    parser.add_argument("--isbn", help="Ustaw identyfikator (ISBN/UUID)")
    parser.add_argument("--series", help="Ustaw nazwę cyklu (pusty łańcuch usuwa serię)")
    parser.add_argument("--series-index", type=float, help="Ustaw numer tomu (np. 2 lub 1.5)")
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Wyświetla metadane, a gdy podano flagi edycji — zapisuje zmiany."""
    try:
        with Epub(args.file) as epub:
            metadata = epub.metadata
            if _apply_edits(metadata, args):
                epub.metadata = metadata
                print(f"Zapisano metadane: {args.file}\n")
            _print_metadata(metadata)
    except (EpubError, OSError, KeyError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
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
    series = metadata.series or "—"
    if metadata.series and metadata.series_index is not None:
        index = (
            str(int(metadata.series_index))
            if metadata.series_index.is_integer()
            else str(metadata.series_index)
        )
        series = f"{metadata.series} #{index}"
    print(f"Tytuł:    {metadata.title or '—'}")
    print(f"Autorzy:  {', '.join(metadata.creators) or '—'}")
    print(f"Język:    {metadata.language or '—'}")
    print(f"Wydawca:  {metadata.publisher or '—'}")
    print(f"Data:     {metadata.date or '—'}")
    print(f"ISBN:     {metadata.identifier or '—'}")
    print(f"Tematy:   {', '.join(metadata.subjects) or '—'}")
    print(f"Cykl:     {series}")
