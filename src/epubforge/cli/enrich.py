"""Subkomenda CLI ``epubforge enrich`` — hurtowe wzbogacanie metadanych.

Wzbogaca pliki/katalogi EPUB albo bibliotekę Calibre (``--calibre-library``) danymi
z :mod:`epubforge.bookmeta` (BN → LC → OL → GB). Przebieg jest sekwencyjny w jednym
procesie, więc współdzielony rate limiter/cache LC obowiązuje cały hurt. ``Ctrl+C``
przerywa kooperacyjnie po bieżącej książce (raport częściowy).
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from pathlib import Path
from types import FrameType

from epubforge.enrich import (
    DEFAULT_FIELDS,
    POLICIES,
    BookOutcome,
    CalibreError,
    EnrichOptions,
    EnrichSummary,
    enrich_library,
    enrich_paths,
    format_outcome_line,
    format_summary,
    normalize_fields,
    write_report,
)
from epubforge.enrich.model import DEFAULT_FIELD_POLICY, DEFAULT_TAGS_POLICY
from epubforge.i18n import _


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``enrich`` w głównym parserze argparse."""
    parser = subparsers.add_parser(
        "enrich", help=_("Hurtowe wzbogacanie metadanych (BN/LubimyCzytac/OpenLibrary/GBooks)")
    )
    parser.add_argument("paths", type=Path, nargs="*", help=_("Pliki lub katalogi EPUB"))
    parser.add_argument(
        "--fields",
        help=_("Pola do wzbogacenia po przecinku, np. tytuł,opis,wydawca (domyślnie: komplet)"),
    )
    parser.add_argument("--tags", action="store_true", help=_("Uzupełnij tagi z taksonomii"))
    parser.add_argument(
        "--policy",
        choices=POLICIES,
        help=_("Polityka scalania (domyślnie: fill dla pól, append dla tagów)"),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help=_("Pokaż plan zmian, nic nie zapisuj")
    )
    parser.add_argument(
        "--report", type=Path, help=_("Zapisz raport do pliku (CSV lub JSON wg rozszerzenia)")
    )
    parser.add_argument(
        "--calibre-library",
        type=Path,
        metavar="PATH",
        help=_("Wzbogać bibliotekę Calibre pod tą ścieżką (wymaga zamkniętego GUI Calibre)"),
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Uruchamia wzbogacanie plików albo biblioteki Calibre i drukuje raport."""
    options = _build_options(args)
    canceller = _Canceller()
    try:
        with canceller:
            if args.calibre_library is not None:
                outcomes, summary = enrich_library(
                    args.calibre_library,
                    options,
                    on_progress=_progress,
                    should_cancel=canceller.cancelled,
                )
            else:
                if not args.paths:
                    print(_("Podaj pliki/katalogi EPUB albo --calibre-library"), file=sys.stderr)
                    return 2
                outcomes, summary = enrich_paths(
                    args.paths,
                    options,
                    on_progress=_progress,
                    should_cancel=canceller.cancelled,
                )
    except CalibreError as exc:
        print(_("Błąd Calibre: {error}").format(error=exc), file=sys.stderr)
        return 1

    _print_results(outcomes, summary, dry_run=options.dry_run)
    if args.report is not None:
        write_report(args.report, outcomes, summary)
        print(_("Raport zapisano: {path}").format(path=args.report))
    return 0


def _build_options(args: argparse.Namespace) -> EnrichOptions:
    """Buduje :class:`EnrichOptions` z argumentów CLI (polityki: --policy nadpisuje domyślne)."""
    fields = normalize_fields(args.fields.split(",")) if args.fields else DEFAULT_FIELDS
    field_policy = args.policy or DEFAULT_FIELD_POLICY
    tags_policy = args.policy or DEFAULT_TAGS_POLICY
    return EnrichOptions(
        fields=fields,
        want_tags=args.tags,
        field_policy=field_policy,
        tags_policy=tags_policy,
        dry_run=args.dry_run,
    )


def _print_results(outcomes: list[BookOutcome], summary: EnrichSummary, *, dry_run: bool) -> None:
    """Drukuje linię planu/wyniku per książka oraz podsumowanie."""
    if dry_run:
        print(_("— PLAN (dry-run, nic nie zapisano) —"))
    for outcome in outcomes:
        print(format_outcome_line(outcome, dry_run=dry_run))
    print(format_summary(summary))


def _progress(done: int, total: int) -> None:
    """Wypisuje pasek postępu na stderr (nie miesza się z raportem na stdout)."""
    print(f"\r[{done}/{total}]", end="", file=sys.stderr, flush=True)
    if done == total:
        print("", file=sys.stderr)


class _Canceller:
    """Kooperacyjne anulowanie przez ``Ctrl+C`` (SIGINT ustawia zdarzenie)."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._previous: object = None

    def cancelled(self) -> bool:
        """Czy zażądano przerwania."""
        return self._event.is_set()

    def __enter__(self) -> _Canceller:
        self._previous = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._on_sigint)
        return self

    def __exit__(self, *exc: object) -> None:
        if callable(self._previous):
            signal.signal(signal.SIGINT, self._previous)

    def _on_sigint(self, _signum: int, _frame: FrameType | None) -> None:
        print(_("\nPrzerywam po bieżącej książce…"), file=sys.stderr)
        self._event.set()
