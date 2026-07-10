"""Subkomenda CLI ``epubforge upgrade`` — modernizacja EPUB 2 → EPUB 3."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from epubforge.converters import UpgradeReport, upgrade_to_epub3
from epubforge.core import Epub, EpubError
from epubforge.i18n import _


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``upgrade`` w głównym parserze argparse."""
    parser = subparsers.add_parser("upgrade", help=_("Uaktualnij pakiet EPUB 2 → EPUB 3"))
    parser.add_argument("file", type=Path, help=_("Plik EPUB do modernizacji"))
    parser.add_argument(
        "--drop-ncx",
        action="store_true",
        help=_("Usuń NCX (plik + wpis manifestu + spine@toc); domyślnie NCX zostaje"),
    )
    parser.add_argument(
        "-o", "--output", type=Path, help=_("Zapisz wynik do nowego pliku zamiast nadpisywać")
    )
    parser.add_argument("--dry-run", action="store_true", help=_("Pokaż plan zmian bez zapisu"))
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Wykonuje modernizację EPUB 2 → 3; zwraca kod wyjścia."""
    try:
        with Epub(args.file) as epub:
            report = upgrade_to_epub3(epub, keep_ncx=not args.drop_ncx)
            if report.already_epub3:
                print(_("Plik jest już w formacie EPUB 3 — nic do zrobienia."))
                return 0
            _print_report(report, dry_run=args.dry_run)
            if args.dry_run:
                print(_("(--dry-run) Nie zapisano zmian."))
                return 0
            saved = epub.save(args.output)
            print(_("Zapisano EPUB 3 do: {path}").format(path=saved))
    except EpubError as exc:
        print(_("Błąd: {error}").format(error=exc), file=sys.stderr)
        return 1
    return 0


def _print_report(report: UpgradeReport, *, dry_run: bool) -> None:
    """Wypisuje listę transformacji i pominięć (plan przy --dry-run)."""
    header = _("Plan modernizacji:") if dry_run else _("Wykonane transformacje:")
    print(header)
    for transformation in report.transformations:
        print(f"  • {transformation}")
    for note in report.skipped:
        print(_("  ⚠ {note}").format(note=note))
