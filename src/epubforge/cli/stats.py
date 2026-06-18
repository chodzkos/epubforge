"""Subkomenda CLI ``epubforge stats`` — statystyki książki i raport HTML."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from epubforge import __version__
from epubforge.core import Epub, EpubError
from epubforge.i18n import _
from epubforge.stats import BookStats, StatsOptions, compute_stats, render_report_html

_TOP_PRINTED = 20


def add_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Rejestruje subkomendę ``stats`` w głównym parserze argparse."""
    parser = subparsers.add_parser("stats", help=_("Statystyki książki (słowa, czas, top-słowa)"))
    parser.add_argument("file", type=Path, help=_("Plik EPUB"))
    parser.add_argument("--report", type=Path, help=_("Zapisz raport HTML do pliku"))
    parser.add_argument("--top", type=int, default=50, help=_("Liczba top-słów (domyślnie 50)"))
    parser.add_argument(
        "--words-per-page", type=int, default=250, help=_("Słów na stronę (domyślnie 250)")
    )
    parser.add_argument(
        "--wpm", type=int, default=200, help=_("Tempo czytania słów/min (domyślnie 200)")
    )
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    """Liczy statystyki, wypisuje podsumowanie i opcjonalnie zapisuje raport HTML."""
    options = StatsOptions(words_per_page=args.words_per_page, wpm=args.wpm, top_n=args.top)
    try:
        with Epub(args.file) as epub:
            stats = compute_stats(epub, options)
    except EpubError as exc:
        print(_("Błąd: {error}").format(error=exc), file=sys.stderr)
        return 1

    _print_summary(stats)
    if args.report is not None:
        args.report.write_text(render_report_html(stats, __version__), encoding="utf-8")
        print(_("Zapisano raport: {path}").format(path=args.report))
    return 0


def _print_summary(stats: BookStats) -> None:
    """Wypisuje liczby zbiorcze i top 20 słów."""
    language = stats.language or "—"
    if stats.language and stats.language_source != "none":
        language = f"{stats.language} ({stats.language_source})"
    print(_("Słowa: {n}").format(n=stats.words))
    print(_("Rozdziały: {n}").format(n=len(stats.chapters)))
    print(_("Szac. strony: {n}").format(n=stats.estimated_pages))
    print(_("Czas czytania: {n} min").format(n=stats.reading_time_min))
    print(_("Język: {lang}").format(lang=language))
    if stats.top_words:
        print(_("Top słowa:"))
        for word, count in stats.top_words[:_TOP_PRINTED]:
            print(f"  {word}: {count}")
