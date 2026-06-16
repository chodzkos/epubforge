"""Subkomenda CLI ``epubforge toc`` — podgląd, generowanie i naprawa spisu treści."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from epubforge.core import Epub, EpubError
from epubforge.i18n import _
from epubforge.toc import (
    TocEntry,
    generate_toc,
    read_toc,
    repair_toc,
    validate_toc,
    write_toc,
)

_DEFAULT_MAX_LEVEL = 3


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``toc`` w głównym parserze argparse."""
    parser = subparsers.add_parser("toc", help=_("Spis treści: podgląd, generowanie, naprawa"))
    parser.add_argument("file", type=Path, help=_("Plik EPUB"))
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--show", action="store_true", help=_("Wypisz bieżący spis treści"))
    action.add_argument(
        "--generate", action="store_true", help=_("Wygeneruj spis z nagłówków dokumentów")
    )
    action.add_argument("--repair", action="store_true", help=_("Usuń martwe wpisy ze spisu"))
    parser.add_argument(
        "--max-level",
        type=int,
        default=_DEFAULT_MAX_LEVEL,
        help=_("Najgłębszy poziom nagłówka przy --generate (1-6, domyślnie 3)"),
    )
    parser.add_argument(
        "--output", type=Path, help=_("Zapisz wynik do nowego pliku zamiast nadpisywać")
    )
    parser.add_argument(
        "--dry-run", action="store_true", help=_("Tylko pokaż zmiany przy --repair, nie zapisuj")
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Wykonuje wybraną akcję spisu treści; zwraca kod wyjścia."""
    try:
        with Epub(args.file) as epub:
            if args.generate:
                return _run_generate(epub, args)
            if args.repair:
                return _run_repair(epub, args)
            return _run_show(epub)
    except EpubError as exc:
        print(_("Błąd: {error}").format(error=exc), file=sys.stderr)
        return 1


def _run_show(epub: Epub) -> int:
    """Wypisuje bieżący spis treści z wcięciami."""
    entries, source = read_toc(epub)
    if not entries:
        print(_("Brak spisu treści w EPUB-ie."))
        return 0
    print(_("Źródło spisu: {source}").format(source=source))
    _print_tree(entries, 0)
    return 0


def _run_generate(epub: Epub, args: argparse.Namespace) -> int:
    """Generuje spis z nagłówków, zapisuje nav+ncx i drukuje wynik."""
    entries = generate_toc(epub, max_level=args.max_level)
    if not entries:
        print(_("Nie znaleziono nagłówków do zbudowania spisu."))
        return 0
    write_toc(epub, entries)
    saved = epub.save(args.output)
    _print_tree(entries, 0)
    print(_("Zapisano spis treści do: {path}").format(path=saved))
    return 0


def _run_repair(epub: Epub, args: argparse.Namespace) -> int:
    """Usuwa martwe wpisy ze spisu (lub tylko je pokazuje przy --dry-run)."""
    entries, _source = read_toc(epub)
    problems = validate_toc(epub, entries)
    if not problems:
        print(_("Spis treści jest poprawny — brak martwych wpisów."))
        return 0
    for problem in problems:
        print(_("✗ {href} — {reason}").format(href=problem.href, reason=problem.reason))
    if args.dry_run:
        print(_("(--dry-run) Nie zapisano zmian."))
        return 0
    repaired, removed = repair_toc(epub, entries)
    write_toc(epub, repaired)
    saved = epub.save(args.output)
    print(_("Usunięto {n} wpisów. Zapisano do: {path}").format(n=len(removed), path=saved))
    return 0


def _print_tree(entries: list[TocEntry], depth: int) -> None:
    """Drukuje drzewo spisu z wcięciami (2 spacje na poziom)."""
    for entry in entries:
        indent = "  " * depth
        target = f"  → {entry.href}" if entry.href else ""
        print(f"{indent}- {entry.title}{target}")
        _print_tree(entry.children, depth + 1)
