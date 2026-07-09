"""Subkomenda CLI ``epubforge typo`` — fixer typografii tekstu."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from epubforge.cli._batch import add_batch_arguments, format_dry_run, run_batch
from epubforge.core import Epub, EpubError
from epubforge.fixers import TypographyOptions, TypographyReport, fix_typography
from epubforge.fixers.typography import (
    RULE_DASHES,
    RULE_ELLIPSIS,
    RULE_NBSP_LETTERS,
    RULE_NBSP_NUMBERS,
    RULE_QUOTES,
)
from epubforge.i18n import _

# Etykiety reguł do raportu CLI (literały gettext dla Babel).
_RULE_LABELS: dict[str, str] = {
    RULE_QUOTES: _("cudzysłowy"),
    RULE_DASHES: _("pauzy"),
    RULE_ELLIPSIS: _("wielokropki"),
    RULE_NBSP_LETTERS: _("twarde spacje (sieroty)"),
    RULE_NBSP_NUMBERS: _("twarde spacje (liczby/jednostki)"),
}


@dataclass(frozen=True)
class _TypographyPayload:
    """Picklowalne opcje pracy dla pojedynczego pliku."""

    options: TypographyOptions
    dry_run: bool
    diff_full: bool


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``typo`` w głównym parserze argparse."""
    parser = subparsers.add_parser("typo", help=_("Popraw typografię tekstu w EPUB"))
    add_batch_arguments(parser, file_help=_("Pliki EPUB do modyfikacji"))
    parser.add_argument(
        "--lang",
        default="pl",
        help=_("Język typografii: pl/en/de (dobiera cudzysłowy; domyślnie: pl)"),
    )
    parser.add_argument(
        "--no-quotes",
        dest="fix_quotes",
        action="store_false",
        help=_("Nie zamieniaj prostych cudzysłowów na typograficzne"),
    )
    parser.add_argument(
        "--no-dashes",
        dest="fix_dashes",
        action="store_false",
        help=_("Nie zamieniaj dywizów na pauzy (dialogi/wtrącenia)"),
    )
    parser.add_argument(
        "--no-ellipsis",
        dest="fix_ellipsis",
        action="store_false",
        help=_("Nie zamieniaj '...' na wielokropek '…'"),
    )
    parser.add_argument(
        "--no-nbsp-letters",
        dest="nbsp_single_letters",
        action="store_false",
        help=_("Nie wstawiaj twardej spacji po samotnych spójnikach (pl)"),
    )
    parser.add_argument(
        "--nbsp-numbers",
        dest="nbsp_numbers_units",
        action="store_true",
        help=_("Twarda spacja między liczbą a jednostką (np. '10 km') — domyślnie wyłączone"),
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
    """Uruchamia fixer typografii z argumentów CLI."""
    options = TypographyOptions(
        language=args.lang,
        fix_quotes=args.fix_quotes,
        fix_dashes=args.fix_dashes,
        fix_ellipsis=args.fix_ellipsis,
        nbsp_single_letters=args.nbsp_single_letters,
        nbsp_numbers_units=args.nbsp_numbers_units,
    )
    payload = _TypographyPayload(
        options=options,
        dry_run=args.dry_run,
        diff_full=args.diff_full,
    )
    return run_batch(
        args.files,
        jobs=args.jobs,
        handler=_run_typography_for_path,
        payload=payload,
    )


def _run_typography_for_path(path: Path, raw_payload: object) -> str:
    """Przetwarza jeden EPUB dla batch runnera."""
    payload = cast(_TypographyPayload, raw_payload)
    try:
        with Epub(path) as epub:
            report = fix_typography(epub, payload.options)
            if payload.dry_run:
                return f"{_format_report(report, path)}\n\n{format_dry_run(epub, diff_full=payload.diff_full)}"
            epub.save()
    except EpubError as exc:
        raise RuntimeError(exc) from exc
    return _format_report(report, path)


def _print_report(report: TypographyReport, path: Path) -> None:
    """Wypisuje podsumowanie podmian per reguła."""
    print(_format_report(report, path))


def _format_report(report: TypographyReport, path: Path) -> str:
    """Zwraca podsumowanie podmian per reguła."""
    if report.total_changes == 0:
        return _("Bez zmian typograficznych: {path}").format(path=path)
    lines = [
        _("Zaktualizowano EPUB: {path} ({count} podmian)").format(
            path=path, count=report.total_changes
        )
    ]
    for rule, count in report.totals().items():
        if count:
            lines.append(f"  • {_RULE_LABELS[rule]}: {count}")
    return "\n".join(lines)
